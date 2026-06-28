import os
import json
import math

def main():
    print("Minecraft Animation Pack Generator (Loop)")
    start_id = int(input("Start map ID: "))
    end_id = int(input("End map ID: "))
    rows = int(input("Rows: "))
    cols = int(input("Cols: "))
    facing = int(input("Facing (0=down,1=up,2=north,3=south,4=west,5=east): "))
    delay = int(input("Delay in ticks (3-5 recommended): "))
    namespace = input("Namespace (e.g., my_anim): ").strip()
    frames_per_segment = int(input("Frames per segment (default 100): ") or 100)
    preload_frames = int(input("Preload frames (0 to disable): ") or 10)

    total_maps = end_id - start_id + 1
    cells_per_frame = rows * cols
    if total_maps % cells_per_frame != 0:
        print("Error: total maps not divisible by cells per frame.")
        return
    total_frames = total_maps // cells_per_frame
    if total_frames <= 0:
        print("Total frames must be > 0.")
        return

    num_segments = math.ceil(total_frames / frames_per_segment)
    print(f"Generating {total_frames} frames, {num_segments} segments, loop enabled.")
    print(f"Preloading {min(preload_frames, total_frames)} frames.")

    func_dir = f"data/{namespace}/functions"
    os.makedirs(func_dir, exist_ok=True)

    # Generate segment files
    for seg_idx in range(1, num_segments + 1):
        start_frame = (seg_idx - 1) * frames_per_segment
        end_frame = min(seg_idx * frames_per_segment, total_frames) - 1
        file_name = f"next_frame_{seg_idx}.mcfunction"
        lines = [
            f"# segment {seg_idx}/{num_segments}, frames {start_frame}-{end_frame}",
            ""
        ]

        for frame in range(start_frame, end_frame + 1):
            base_map = start_id + frame * cells_per_frame
            cond = f"execute if score #frame_index {namespace} matches {frame} run"
            lines.append(f"# frame {frame}")
            idx = 0
            for row in range(1, rows + 1):
                for col in range(1, cols + 1):
                    map_id = base_map + idx
                    lines.append(f"{cond} data modify entity @e[type=item_frame,tag={row}_{col},limit=1] Item.tag.map set value {map_id}")
                    idx += 1
            lines.append("")

        lines.append("# increment frame index")
        lines.append(f"execute unless score #frame_index {namespace} matches {total_frames}.. run scoreboard players add #frame_index {namespace} 1")
        lines.append("")

        if seg_idx < num_segments:
            next_seg = seg_idx + 1
            lines.append(f"# schedule next segment {next_seg}")
            lines.append(f"execute unless score #frame_index {namespace} matches {total_frames}.. run schedule function {namespace}:next_frame_{next_seg} {delay}t")
        else:
            lines.append("# last segment: loop")
            lines.append(f"execute if score #frame_index {namespace} matches {total_frames} run scoreboard players set #frame_index {namespace} 0")
            lines.append(f"execute if score #frame_index {namespace} matches {total_frames} run schedule function {namespace}:next_frame_1 {delay}t")
            lines.append(f"execute unless score #frame_index {namespace} matches {total_frames}.. run schedule function {namespace}:next_frame_{seg_idx} {delay}t")

        with open(f"{func_dir}/{file_name}", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # Generate reset.mcfunction (summon frames, set initial map)
    clear_cmds = [f"schedule clear {namespace}:next_frame_{i}" for i in range(1, num_segments + 1)]

    summon_lines = []
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            x_off = (row - (rows + 1) / 2) * 1.0
            z_off = (col - (cols + 1) / 2) * 1.0
            x_str = f"{x_off:+.1f}" if x_off != 0 else "~"
            z_str = f"{z_off:+.1f}" if z_off != 0 else "~"
            summon_lines.append(
                f"summon minecraft:item_frame ~{x_str} ~ ~{z_str} {{Facing:{facing},Tags:[\"anim_frame\",\"{row}_{col}\"]}}"
            )

    set_map_lines = []
    idx = 0
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            map_id = start_id + idx
            set_map_lines.append(
                f"data modify entity @e[type=item_frame,tag={row}_{col},limit=1] Item set value {{id:\"minecraft:filled_map\",Count:1b,tag:{{map:{map_id}}}}}"
            )
            idx += 1

    reset_content = f"""# reset: kill old frames, summon new, set frame 0
kill @e[type=item_frame,tag=anim_frame]
{chr(10).join(summon_lines)}
forceload add ~ ~
{chr(10).join(set_map_lines)}
scoreboard players set #frame_index {namespace} 0
{chr(10).join(clear_cmds)}
"""
    with open(f"{func_dir}/reset.mcfunction", "w", encoding="utf-8") as f:
        f.write(reset_content)

    # Generate init.mcfunction (scoreboard, call reset, preload, start)
    preload_lines = []
    if preload_frames > 0:
        actual_preload = min(preload_frames, total_frames)
        preload_lines.append("# preload maps")
        for frame in range(actual_preload):
            base_map = start_id + frame * cells_per_frame
            for i in range(cells_per_frame):
                map_id = base_map + i
                preload_lines.append(f"give @s minecraft:filled_map{{CustomMapData:{map_id}}} 1")
        preload_lines.append("clear @s minecraft:filled_map")
        preload_lines.append("")

    init_content = f"""# init: create scoreboard, call reset, preload, start
scoreboard objectives add {namespace} dummy
function {namespace}:reset
{chr(10).join(preload_lines)}
tellraw @a {{"text":"[Anim] Initialized {rows}x{cols}, {total_frames} frames (loop)","color":"green"}}
schedule function {namespace}:next_frame_1 {delay}t
"""
    with open(f"{func_dir}/init.mcfunction", "w", encoding="utf-8") as f:
        f.write(init_content)

    # stop.mcfunction
    stop_clear = "\n".join(clear_cmds)
    stop_content = f"""# stop
tellraw @a {{"text":"[Anim] Stopped","color":"red"}}
{stop_clear}
scoreboard players set #frame_index {namespace} {total_frames}
"""
    with open(f"{func_dir}/stop.mcfunction", "w", encoding="utf-8") as f:
        f.write(stop_content)

    # pack.mcmeta
    mcmeta = {
        "pack": {
            "pack_format": 10,
            "description": f"{namespace} animation ({rows}x{cols}, {total_frames} frames, loop)"
        }
    }
    with open("pack.mcmeta", "w", encoding="utf-8") as f:
        json.dump(mcmeta, f, indent=2)

    print(f"Done. {num_segments} segment files generated.")
    print("Place 'data' and 'pack.mcmeta' into a folder inside datapacks.")
    print(f"Run /reload, then /function {namespace}:init")

if __name__ == "__main__":
    main()