import bpy

from . import ObjectModeOnly, Steps
from ..core.engine import load_config
from ..core.state import clear_results
from ..operations.topology import clean_topology, retopologize_steps
from ..ui.redraw import redraw_view3d


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


class ASSET_VALIDATOR_OT_retopologize(ObjectModeOnly, Steps, bpy.types.Operator):
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

    # Modal (Steps): a car is thousands of loose parts and a QuadriFlow run each, in a worker process.
    # Esc closes _work, which frees the half-done object's data and kills the worker; finished objects stay

    def _begin(self, context) -> bool:
        self._objects = _selected_meshes(context)
        if not self._objects:
            self.report({"ERROR"}, "Select at least one mesh object first")
            return False
        self._created, self._notes, self._failed = [], [], []
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
