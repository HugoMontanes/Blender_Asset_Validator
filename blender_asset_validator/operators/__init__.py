import time

import bpy

from ..core.state import clear_results
from ..ui.redraw import redraw_view3d

_NAVIGATION = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM", "NDOF_MOTION", "MOUSEMOVE"}


class ObjectModeOnly:
    """Operator mixin: in Edit Mode `mesh.polygons` is stale and bmesh.to_mesh fails."""

    @classmethod
    def poll(cls, context):
        if context.mode == "OBJECT":
            return True
        cls.poll_message_set("Switch to Object Mode first")
        return False


class Steps:
    """Operator mixin for long runs: invoke runs the generator self._work() on a timer, its status
    lines in the status bar, Esc to cancel; execute (scripts, the redo panel) runs it in one go.
    Subclasses give _begin(context) -> bool and _work(); the default _finish reports self._lines."""

    def invoke(self, context, event):
        self._timer, self._cancelled, self._lines = None, False, []
        if not self._begin(context):
            return {"CANCELLED"}
        self._jobs = self._work()
        self._timer = context.window_manager.event_timer_add(0.02, window=context.window)
        context.window_manager.modal_handler_add(self)
        self._status = f"{self.bl_label}: starting — Esc to cancel"
        context.workspace.status_text_set(self._status)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._jobs.close()
            self._cancelled = True
            return self._end(context)
        if event.type in _NAVIGATION and not (event.ctrl or event.alt or event.oskey):  # Alt+Wheel changes frame
            return {"PASS_THROUGH"}
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}  # the scene must not change under the running job
        try:
            status = next(self._jobs)
            if status != self._status:
                self._status = status
                context.workspace.status_text_set(status)
        except StopIteration:
            return self._end(context)
        except Exception:
            self._end(context)  # or the timer keeps firing and the status bar stays stuck
            raise
        return {"RUNNING_MODAL"}

    def cancel(self, context):  # Blender closing mid-run
        self._jobs.close()
        context.window_manager.event_timer_remove(self._timer)
        context.workspace.status_text_set(None)

    def execute(self, context):
        self._timer, self._cancelled, self._lines = None, False, []
        if not self._begin(context):
            return {"CANCELLED"}
        for _ in self._work():
            time.sleep(0.01)  # Retopologize's steps mostly wait on its worker
        return self._finish(context)

    def _end(self, context):
        context.window_manager.event_timer_remove(self._timer)
        context.workspace.status_text_set(None)
        return self._finish(context)

    def _each(self, objects, steps_of):
        """Runs steps_of(obj) for each object, yielding status lines; their notes go to self._lines."""
        for number, obj in enumerate(objects, 1):
            name, steps = obj.name, steps_of(obj)
            try:
                while True:
                    yield f"{self.bl_label} '{name}' ({number}/{len(objects)}): {next(steps)} — Esc to cancel"
            except StopIteration as end:
                self._lines.append(f"'{name}': {end.value}")
            finally:
                steps.close()

    def _finish(self, context):
        print("\n".join(self._lines))
        clear_results()  # the meshes changed under the old results
        redraw_view3d(context)
        if self._cancelled:
            self.report({"WARNING"}, f"{self.bl_label} cancelled: {len(self._lines)} mesh(es) done, the one it was on is back as it was")
        else:
            self.report({"INFO"}, self._lines[0] if len(self._lines) == 1 else "; ".join(self._lines))
        return {"FINISHED"} if self._lines else {"CANCELLED"}


def restorable(obj: bpy.types.Object, steps):
    """Yields from steps and returns its result. Stopped halfway (Esc, an error), obj's mesh is put
    back from a copy taken first: a half-run Auto Unwrap leaves UV0 unpacked and half unwrapped.
    user_remap swaps the copy in for every user, so linked duplicates stay linked."""
    backup = obj.data.copy()
    try:
        return (yield from steps)
    except BaseException:
        mesh, name = obj.data, obj.data.name
        mesh.user_remap(backup)
        bpy.data.meshes.remove(mesh)
        backup.name, backup = name, None
        raise
    finally:
        if backup is not None:
            bpy.data.meshes.remove(backup)
