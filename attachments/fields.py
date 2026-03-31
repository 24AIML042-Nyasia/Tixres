from django.contrib.contenttypes.fields import GenericRelation


class SafeGenericRelation(GenericRelation):
    """
    Wrapper around GenericRelation that drops from_fields/to_fields during
    deconstruction to avoid Django re-construction conflicts (Django 6.0.3
    currently passes from_fields twice when cloning GenericRelation).
    """

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop("from_fields", None)
        kwargs.pop("to_fields", None)
        return name, path, args, kwargs
