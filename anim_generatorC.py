# -*- coding: utf-8 -*-
import os
import json
import math

def main():
    print("Minecraft 动画数据包生成器（无限循环）")
    start_id = int(input("起始地图 ID: "))
    end_id = int(input("结束地图 ID: "))
    rows = int(input("行数（垂直）: "))
    cols = int(input("列数（水平）: "))
    facing = int(input("展示框朝向 (0=下,1=上,2=北,3=南,4=西,5=东): "))
    delay = int(input("每帧延迟 (刻, 推荐 3~5): "))
    namespace = input("命名空间 (如 my_anim): ").strip()
    frames_per_segment = int(input("每段帧数 (默认 100): ") or 100)
    preload_frames = int(input("预加载帧数 (0 表示禁用): ") or 10)

    total_maps = end_id - start_id + 1
    cells_per_frame = rows * cols
    if total_maps % cells_per_frame != 0:
        print("错误：地图总数不能被每帧格子数整除！")
        return
    total_frames = total_maps // cells_per_frame
    if total_frames <= 0:
        print("总帧数必须大于 0！")
        return

    num_segments = math.ceil(total_frames / frames_per_segment)
    print(f"将生成 {total_frames} 帧，分为 {num_segments} 段，无限循环。")
    print(f"预加载前 {min(preload_frames, total_frames)} 帧地图。")

    func_dir = f"data/{namespace}/functions"
    os.makedirs(func_dir, exist_ok=True)

    # 生成分段文件
    for seg_idx in range(1, num_segments + 1):
        start_frame = (seg_idx - 1) * frames_per_segment
        end_frame = min(seg_idx * frames_per_segment, total_frames) - 1
        file_name = f"next_frame_{seg_idx}.mcfunction"
        lines = [
            f"# 段 {seg_idx}/{num_segments}，帧 {start_frame}~{end_frame}",
            ""
        ]

        for frame in range(start_frame, end_frame + 1):
            base_map = start_id + frame * cells_per_frame
            cond = f"execute if score #frame_index {namespace} matches {frame} run"
            lines.append(f"# 帧 {frame}")
            idx = 0
            for row in range(1, rows + 1):
                for col in range(1, cols + 1):
                    map_id = base_map + idx
                    lines.append(f"{cond} data modify entity @e[type=item_frame,tag={row}_{col},limit=1] Item.tag.map set value {map_id}")
                    idx += 1
            lines.append("")

        lines.append("# 帧索引递增")
        lines.append(f"execute unless score #frame_index {namespace} matches {total_frames}.. run scoreboard players add #frame_index {namespace} 1")
        lines.append("")

        if seg_idx < num_segments:
            next_seg = seg_idx + 1
            lines.append(f"# 调度下一段 {next_seg}")
            lines.append(f"execute unless score #frame_index {namespace} matches {total_frames}.. run schedule function {namespace}:next_frame_{next_seg} {delay}t")
        else:
            lines.append("# 最后一段：循环")
            lines.append(f"execute if score #frame_index {namespace} matches {total_frames} run scoreboard players set #frame_index {namespace} 0")
            lines.append(f"execute if score #frame_index {namespace} matches {total_frames} run schedule function {namespace}:next_frame_1 {delay}t")
            lines.append(f"execute unless score #frame_index {namespace} matches {total_frames}.. run schedule function {namespace}:next_frame_{seg_idx} {delay}t")

        with open(f"{func_dir}/{file_name}", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # 生成 reset.mcfunction（召唤展示框、设置初始地图）
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

    reset_content = f"""# reset: 清理旧框，召唤新框，设置第0帧
kill @e[type=item_frame,tag=anim_frame]
{chr(10).join(summon_lines)}
forceload add ~ ~
{chr(10).join(set_map_lines)}
scoreboard players set #frame_index {namespace} 0
{chr(10).join(clear_cmds)}
"""
    with open(f"{func_dir}/reset.mcfunction", "w", encoding="utf-8") as f:
        f.write(reset_content)

    # 生成 init.mcfunction（创建计分板、调用 reset、预加载、启动）
    preload_lines = []
    if preload_frames > 0:
        actual_preload = min(preload_frames, total_frames)
        preload_lines.append("# 预加载地图")
        for frame in range(actual_preload):
            base_map = start_id + frame * cells_per_frame
            for i in range(cells_per_frame):
                map_id = base_map + i
                preload_lines.append(f"give @s minecraft:filled_map{{CustomMapData:{map_id}}} 1")
        preload_lines.append("clear @s minecraft:filled_map")
        preload_lines.append("")

    init_content = f"""# init: 创建计分板，调用 reset，预加载，启动
scoreboard objectives add {namespace} dummy
function {namespace}:reset
{chr(10).join(preload_lines)}
tellraw @a {{"text":"[动画] 初始化完成 {rows}×{cols}，共 {total_frames} 帧（循环）","color":"green"}}
schedule function {namespace}:next_frame_1 {delay}t
"""
    with open(f"{func_dir}/init.mcfunction", "w", encoding="utf-8") as f:
        f.write(init_content)

    # stop.mcfunction
    stop_clear = "\n".join(clear_cmds)
    stop_content = f"""# stop
tellraw @a {{"text":"[动画] 已停止","color":"red"}}
{stop_clear}
scoreboard players set #frame_index {namespace} {total_frames}
"""
    with open(f"{func_dir}/stop.mcfunction", "w", encoding="utf-8") as f:
        f.write(stop_content)

    # pack.mcmeta
    mcmeta = {
        "pack": {
            "pack_format": 10,
            "description": f"{namespace} 动画 ({rows}×{cols}，{total_frames} 帧，循环)"
        }
    }
    with open("pack.mcmeta", "w", encoding="utf-8") as f:
        json.dump(mcmeta, f, indent=2)

    print(f"完成！共生成 {num_segments} 个分段文件。")
    print("请将 'data' 和 'pack.mcmeta' 放入 datapacks 下的一个文件夹中。")
    print(f"进入游戏后执行 /reload，然后 /function {namespace}:init")

if __name__ == "__main__":
    main()