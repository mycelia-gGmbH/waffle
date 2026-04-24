from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework import serializers
from badgeuser.serializers_v1 import (
    BadgeUserFullNameFieldV1,
)
from issuer.serializers_v1 import (
    BadgeInstanceSerializerV1,
    QrCodeSerializerV1,
    LearningPathSerializerV1,
)
from issuer.models import (
    Issuer,
    BadgeInstance,
    QrCode,
    LearningPath,
    RequestedBadge,
)
from mainsite.drf_fields import ValidImageField
from mainsite.serializers import (
    DateTimeWithUtcZAtEndField,
    ExcludeFieldsMixin,
    StripTagsCharField,
)
from django.core.validators import MaxValueValidator, MinValueValidator
from mainsite.validators import (
    ChoicesValidator,
    ValidImageValidator,
)
from .models import (
    PDFTemplate,
    PDFEditorBadgeInstance,
    PDFEditorQrCode,
    PDFEditorLearningPath,
)


class PDFTemplateSerializerV1(ExcludeFieldsMixin, serializers.Serializer):
    created_at = DateTimeWithUtcZAtEndField(read_only=True)
    updated_at = DateTimeWithUtcZAtEndField(read_only=True)
    created_by = BadgeUserFullNameFieldV1(read_only=True)
    issuer_id = serializers.CharField(max_length=254)

    slug = StripTagsCharField(max_length=255, read_only=True, source="entity_id")
    name = StripTagsCharField(max_length=255)
    format = serializers.IntegerField(
        validators=[ChoicesValidator(list(dict(PDFTemplate.FORMAT_CHOICES).keys()), True)],
        default=PDFTemplate.FORMAT_PORTRAIT,
    )
    alignment = serializers.IntegerField(
        validators=[ChoicesValidator(list(dict(PDFTemplate.ALIGNMENT_CHOICES).keys()), True)],
        default=PDFTemplate.ALIGNMENT_LEFT,
    )
    posX = serializers.IntegerField(
        validators=[
            MinValueValidator(PDFTemplate.POSX_MINIMUM),
            MaxValueValidator(PDFTemplate.POSX_MAXIMUM),
        ],
        default=PDFTemplate.POSX_DEFAULT,
    )
    posY = serializers.IntegerField(
        validators=[
            MinValueValidator(PDFTemplate.POSY_MINIMUM),
            MaxValueValidator(PDFTemplate.POSY_MAXIMUM),
        ],
        default=PDFTemplate.POSY_DEFAULT,
    )
    scale = serializers.IntegerField(
        validators=[
            MinValueValidator(PDFTemplate.SCALE_MINIMUM),
            MaxValueValidator(PDFTemplate.SCALE_MAXIMUM),
        ],
        default=PDFTemplate.SCALE_DEFAULT,
    )
    image = ValidImageField(
        required=True,
        validators=[ValidImageValidator(['PNG', 'JPEG'])]
    )
    used = serializers.BooleanField(
        read_only=True, source="is_used"
    )

    class Meta:
        apispec_definition = ("PDFTemplate", {})

    def create(self, validated_data, **kwargs):
        name = validated_data.get("name")
        format = validated_data.get("format")
        alignment = validated_data.get("alignment")
        posX = validated_data.get("posX")
        posY = validated_data.get("posY")
        scale = validated_data.get("scale")
        image = validated_data.get("image")
        created_by = self.context["request"].user
        issuer_id = validated_data.get("issuer_id")

        try:
            issuer = Issuer.objects.get(entity_id=issuer_id)
        except Issuer.DoesNotExist:
            raise serializers.ValidationError(
                f"Issuer with ID '{issuer_id}' does not exist."
            )

        new_pdftemplate = PDFTemplate.objects.create(
            name=name,
            format=format,
            alignment=alignment,
            posX=posX,
            posY=posY,
            scale=scale,
            image=image,
            created_by=created_by,
            issuer=issuer,
        )

        return new_pdftemplate

    def update(self, instance, validated_data):
        instance.name = validated_data.get("name", instance.name)
        instance.format = validated_data.get("format", instance.format)
        instance.alignment = validated_data.get("alignment", instance.alignment)
        instance.posX = validated_data.get("posX", instance.posX)
        instance.posY = validated_data.get("posY", instance.posY)
        instance.scale = validated_data.get("scale", instance.scale)
        instance.image = validated_data.get("image", instance.image)
        instance.save()

        return instance


class PDFEditorBadgeInstanceSerializerV1(BadgeInstanceSerializerV1):
    pdftemplate = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    request_entity_id = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        pdftemplateSlug = data.get("pdftemplate")
        if pdftemplateSlug is not None:
            try:
                pdftemplate = PDFTemplate.objects.get(entity_id=pdftemplateSlug)
            except ObjectDoesNotExist:
                raise serializers.ValidationError('PDFTemplate does not exist.')

        return super(PDFEditorBadgeInstanceSerializerV1, self).validate(data)

    def create(self, validated_data, **kwargs):
        pdftemplate = None
        if validated_data.get("pdftemplate") is not None:
            pdftemplate = PDFTemplate.objects.get(entity_id=validated_data.get("pdftemplate"))

        if validated_data.get("request_entity_id") is not None:
            try:
                requestedBadge = RequestedBadge.objects.get(entity_id=validated_data.get("request_entity_id"))
                qrcode = requestedBadge.qrcode
                pdfeditorQrCode = PDFEditorQrCode.objects.get(qrcode=qrcode)
                if pdfeditorQrCode.pdftemplate is not None:
                    pdftemplate = pdfeditorQrCode.pdftemplate
            except ObjectDoesNotExist:
                pass

        def save_pdftemplate(sender, instance, created, **kwargs):
            if created:
                PDFEditorBadgeInstance.objects.get_or_create(
                    badgeinstance=instance,
                    defaults={
                        "pdftemplate": pdftemplate
                    },
                )
            post_save.disconnect(save_pdftemplate, sender=BadgeInstance)

        post_save.connect(save_pdftemplate, sender=BadgeInstance)
        new_badgeinstance = super(PDFEditorBadgeInstanceSerializerV1, self).create(validated_data, **kwargs)
        post_save.disconnect(save_pdftemplate, sender=BadgeInstance)

        return new_badgeinstance

    def update(self, instance, validated_data):
        pdftemplate = None
        if 'pdftemplate' in validated_data and validated_data.get("pdftemplate") is not None:
            pdftemplate = PDFTemplate.objects.get(entity_id=validated_data.get("pdftemplate"))

        try:
            instance.pdfeditorbadgeinstance.pdftemplate = pdftemplate
            instance.pdfeditorbadgeinstance.save()
        except ObjectDoesNotExist:
            PDFEditorBadgeInstance.objects.create(
                badgeinstance=instance,
                pdftemplate=pdftemplate,
            )

        return super(PDFEditorBadgeInstanceSerializerV1, self).update(instance, validated_data)

    @property
    def data(self):
        data = super(PDFEditorBadgeInstanceSerializerV1, self).data
        pdftemplate = None
        try:
            badgeinstance = BadgeInstance.objects.get(entity_id=data['slug'])
            pbi = PDFEditorBadgeInstance.objects.get(badgeinstance=badgeinstance)
            if pbi.pdftemplate is not None:
                pdftemplate = pbi.pdftemplate.entity_id
        except ObjectDoesNotExist:
            pass

        data['pdftemplate'] = pdftemplate
        return data


class PDFEditorQrCodeSerializerV1(QrCodeSerializerV1):
    pdftemplate = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        pdftemplateSlug = data.get("pdftemplate")
        if pdftemplateSlug is not None:
            try:
                pdftemplate = PDFTemplate.objects.get(entity_id=pdftemplateSlug)
            except ObjectDoesNotExist:
                raise serializers.ValidationError('PDFTemplate does not exist.')

        return data

    def create(self, validated_data, **kwargs):
        new_qrcode = super(PDFEditorQrCodeSerializerV1, self).create(validated_data, **kwargs)
        pdftemplate = None
        if validated_data.get("pdftemplate") is not None:
            pdftemplate = PDFTemplate.objects.get(entity_id=validated_data.get("pdftemplate"))

        PDFEditorQrCode.objects.create(
            qrcode=new_qrcode,
            pdftemplate=pdftemplate,
        )

        return new_qrcode

    def update(self, instance, validated_data):
        pdftemplate = None
        if 'pdftemplate' in validated_data and validated_data.get("pdftemplate") is not None:
            pdftemplate = PDFTemplate.objects.get(entity_id=validated_data.get("pdftemplate"))

        try:
            instance.pdfeditorqrcode.pdftemplate = pdftemplate
            instance.pdfeditorqrcode.save()
        except ObjectDoesNotExist:
            PDFEditorQrCode.objects.create(
                qrcode=instance,
                pdftemplate=pdftemplate,
            )

        return super(PDFEditorQrCodeSerializerV1, self).update(instance, validated_data)

    @property
    def data(self):
        data = super(PDFEditorQrCodeSerializerV1, self).data
        pdftemplate = None
        try:
            qrcode = QrCode.objects.get(entity_id=data['slug'])
            pdftemplate = PDFEditorQrCode.objects.get(qrcode=qrcode).pdftemplate.entity_id
        except (ObjectDoesNotExist, AttributeError):
            pass

        data['pdftemplate'] = pdftemplate
        return data


class PDFEditorLearningPathSerializerV1(LearningPathSerializerV1):
    pdftemplate = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        pdftemplateSlug = data.get("pdftemplate")
        if pdftemplateSlug is not None:
            try:
                pdftemplate = PDFTemplate.objects.get(entity_id=pdftemplateSlug)
            except ObjectDoesNotExist:
                raise serializers.ValidationError('PDFTemplate does not exist.')

        return data

    def create(self, validated_data, **kwargs):
        new_learningpath = super(PDFEditorLearningPathSerializerV1, self).create(validated_data, **kwargs)
        pdftemplate = None
        if validated_data.get("pdftemplate") is not None:
            pdftemplate = PDFTemplate.objects.get(entity_id=validated_data.get("pdftemplate"))

        PDFEditorLearningPath.objects.create(
            learningpath=new_learningpath,
            pdftemplate=pdftemplate,
        )

        return new_learningpath

    def update(self, instance, validated_data):
        pdftemplate = None
        if 'pdftemplate' in validated_data and validated_data.get("pdftemplate") is not None:
            pdftemplate = PDFTemplate.objects.get(entity_id=validated_data.get("pdftemplate"))

        try:
            instance.pdfeditorlearningpath.pdftemplate = pdftemplate
            instance.pdfeditorlearningpath.save()
        except ObjectDoesNotExist:
            PDFEditorLearningPath.objects.create(
                learningpath=instance,
                pdftemplate=pdftemplate,
            )

        badge_instances = BadgeInstance.objects.filter(badgeclass=instance.participationBadge)
        for badgeinstance in badge_instances:
            try:
                pbi = PDFEditorBadgeInstance.objects.get(badgeinstance=badgeinstance)
                pbi.pdftemplate = pdftemplate
                pbi.save()
            except ObjectDoesNotExist:
                PDFEditorBadgeInstance.objects.create(
                    badgeinstance=badgeinstance,
                    pdftemplate=pdftemplate,
                )

        return super(PDFEditorLearningPathSerializerV1, self).update(instance, validated_data)

    @property
    def data(self):
        data = super(PDFEditorLearningPathSerializerV1, self).data
        pdftemplate = None
        try:
            learningpath = LearningPath.objects.get(entity_id=data['slug'])
            pdftemplate = PDFEditorLearningPath.objects.get(learningpath=learningpath).pdftemplate
            if pdftemplate is not None:
                pdftemplate = pdftemplate.entity_id
        except ObjectDoesNotExist:
            pass

        data['pdftemplate'] = pdftemplate
        return data
