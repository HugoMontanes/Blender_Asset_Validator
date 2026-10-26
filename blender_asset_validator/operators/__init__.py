class ObjectModeOnly:
    """Operator mixin: in Edit Mode `mesh.polygons` is stale and bmesh.to_mesh fails."""

    @classmethod
    def poll(cls, context):
        if context.mode == "OBJECT":
            return True
        cls.poll_message_set("Switch to Object Mode first")
        return False
