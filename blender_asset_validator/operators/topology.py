import time

import bpy

from . import ObjectModeOnly
from ..core.engine import load_config
from ..core.state import clear_results
from ..operations.topology import clean_topology, retopologize_steps
from ..ui.redraw import redraw_view3d


_NAVIGATION = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM", "NDOF_MOTION", "MOUSEMOVE"}


def _selected_meshes(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


class ASSET_VALIDATOR_OT_clean_topology(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.clean_topology"
    bl_label = "Clean Topology"
    bl_description = (
        "Tris to quads, dissolve flat edge loops and relax the edge flow along the surface. "
        "Keeps shape, UVs, seams, sharp edges and materials. Works on LODs too"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        config = load_config()
        objects = _selected_meshes(context)
        if not objects:
            self.report({"ERROR"}, "Select at least one mesh object first")
            return {"CANCELLED"}

        cleaned, lines = set(), []
        for obj in objects:
            if obj.data in cleaned:
                continue  # linked duplicates share the mesh — clean it once
            cleaned.add(obj.data)
            lines.append(f"'{obj.name}': {clean_topology(obj, config)}")
        print("\n".join(lines))

        clear_results()  # the meshes changed under the old results
        redraw_view3d(context)
        self.report({"INFO"}, lines[0] if len(lines) == 1 else f"Cleaned {len(lines)} meshes — {'; '.join(lines)}")
        return {"FINISHED"}


class ASSET_VALIDATOR_OT_retopologize(ObjectModeOnly, bpy.types.Operator):
    bl_idname = "asset_validator.retopologize"
    bl_label = "Retopologize"
    bl_description = (
        "Build a new all-quads '<name>_Retopo' object whose edge flow follows the curvature (QuadriFlow), "
        "with materials, UVs and normals resampled from the original. The original is hidden. "
        "QuadriFlow runs in a background Blender, part by part, with progress in the status bar; Esc cancels"
    )
    bl_options = {"REGISTER", "UNDO"}

    ratio: bpy.props.FloatProperty(
        name="Triangle Ratio", description="Target triangle count as a fraction of the original",
        default=0.5, min=0.01, max=2.0,
    )
    use_symmetry: bpy.props.BoolProperty(name="Symmetry", description="Mirror the result on X", default=False)

    def invoke(self, context, event):
        # A car is thousands of loose parts and a QuadriFlow run each, in a worker process:
        # polling it on a timer keeps Blender responsive and shows where it is
        if not self._begin(context):
            return {"CANCELLED"}
        self._jobs = self._work()
        self._timer = context.window_manager.event_timer_add(0.02, window=context.window)
        context.window_manager.modal_handler_add(self)
        self._status = "Retopologize: preparing the mesh — Esc to cancel"
        context.workspace.status_text_set(self._status)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._jobs.close()  # frees the half-done object's data; finished objects stay
            self._cancelled = True
            return self._finish(context)
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
            return self._finish(context)
        except Exception:
            self._finish(context)  # or the timer keeps firing and the status bar stays stuck
            raise
        return {"RUNNING_MODAL"}

    def cancel(self, context):  # Blender closing mid-run: the cleanup also kills the worker
        self._jobs.close()
        context.window_manager.event_timer_remove(self._timer)
        context.workspace.status_text_set(None)

    def execute(self, context):  # scripts and the redo panel: all in one go
        if not self._begin(context):
            return {"CANCELLED"}
        for _ in self._work():
            time.sleep(0.01)  # mostly waiting on the worker
        return self._finish(context)

    def _begin(self, context) -> bool:
        self._objects = _selected_meshes(context)
        if not self._objects:
            self.report({"ERROR"}, "Select at least one mesh object first")
            return False
        self._created, self._notes, self._failed, self._cancelled, self._timer = [], [], [], False, None
        return True

    def _work(self):
        """Retopologizes the objects in turn, yielding a status line while QuadriFlow runs."""
        merge_distance = load_config().get("optimization", {}).get("merge_distance", 0.0001)
        for number, obj in enumerate(self._objects, 1):
            steps = retopologize_steps(obj, self.ratio, self.use_symmetry, merge_distance)
            try:
                while True:
                    done, total = next(steps)
                    step = f"part {done + 1} of {total}" if done < total else "rebuilding UVs and normals"
                    yield f"Retopologize '{obj.name}' ({number}/{len(self._objects)}): {step} — Esc to cancel"
            except StopIteration as end:
                new, note = end.value
                self._created.append(new)
                self._notes.append(f"'{obj.name}': {note}")
                obj.hide_set(True)
            except (RuntimeError, OSError) as e:  # OSError: temp folder full or unwritable
                self._failed.append(f"'{obj.name}': {str(e).strip().splitlines()[-1]}")
            finally:
                steps.close()

    def _finish(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            context.workspace.status_text_set(None)
        print("\n".join(self._notes + self._failed))

        if self._created:
            for obj in self._objects:
                obj.select_set(False)
            for new in self._created:
                new.select_set(True)
            context.view_layer.objects.active = self._created[0]

        clear_results()
        redraw_view3d(context)
        if self._cancelled:
            self.report({"WARNING"}, f"Retopologize cancelled — kept {len(self._created)} finished object(s)")
        elif self._failed:
            self.report({"WARNING"}, f"Retopologized {len(self._created)}, failed {len(self._failed)} — " + "; ".join(self._failed))
        else:
            self.report({"INFO"}, self._notes[0] if len(self._notes) == 1
                        else f"Created {len(self._created)} retopologized object(s) — {'; '.join(self._notes)}")
        return {"FINISHED"} if self._created else {"CANCELLED"}
