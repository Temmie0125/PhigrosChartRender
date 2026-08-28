"""RPE 与官谱 JSON 的读取、格式检测及内部数据模型转换。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import (
    BPMEvent,
    ChartData,
    EventData,
    EventLayer,
    JudgeLineData,
    MetaData,
    NoteData,
)
from .time_utils import timet_to_beats
from .constants import GAME_X_MAX, OFFICIAL_TO_RPE_X_SCALE

logger = logging.getLogger("rpe_render")

# Note 类型常量
NOTE_TAP = 1
NOTE_HOLD = 2
NOTE_FLICK = 3
NOTE_DRAG = 4


def parse_chart(file_path: str | Path) -> ChartData:
    """解析 RPE JSON 谱面文件。

    处理步骤:
        1. 读取 JSON 文件
        2. 验证顶层结构（BPMList, META, judgeLineList 必填）
        3. 解析 MetaData
        4. 解析 BPMList
        5. 解析每条判定线（4 个 eventLayers + notes）
        6. 返回 ChartData

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON 格式错误
        ValueError: 数据结构不符合预期（缺少必要字段等）
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Chart file not found: {path}")

    # 先按标准 JSON 读取以识别格式；官谱再按其运行时约定保留重复键的
    # 首次出现值。RPE 继续使用 Python/JSON 的标准“后者覆盖前者”语义。
    with open(path, "r", encoding="utf-8") as fp:
        text = fp.read()
    raw = json.loads(text)

    if not isinstance(raw, dict):
        raise ValueError("Top-level JSON must be an object")

    if _is_official_chart(raw):
        raw = json.loads(text, object_pairs_hook=_first_key_object)
        chart = _parse_official_chart(raw)
        logger.info(
            "Parsed official chart: %d judge lines (formatVersion=%d)",
            len(chart.judge_line_list), chart.format_version,
        )
        return chart

    # ---- 顶层结构验证 ----
    for required in ("BPMList", "META", "judgeLineList"):
        if required not in raw:
            raise ValueError(f"Missing required field: {required}")

    raw_bpm_list = raw["BPMList"]
    if not raw_bpm_list:
        raise ValueError("BPMList cannot be empty")

    meta = _parse_meta(raw["META"])
    bpm_list = parse_bpm_list(raw_bpm_list)
    judge_line_group = [str(g) for g in raw.get("judgeLineGroup", [])]
    judge_line_list = [parse_judge_line(item) for item in raw["judgeLineList"]]
    _validate_parent_links(judge_line_list)

    logger.info(
        "Parsed chart: %d judge lines, %d BPM events",
        len(judge_line_list),
        len(bpm_list),
    )

    return ChartData(
        bpm_list=bpm_list,
        meta=meta,
        judge_line_group=judge_line_group,
        judge_line_list=judge_line_list,
    )


def _first_key_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """构造 JSON 对象时保留重复键的第一个值（官谱约定）。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key not in result:
            result[key] = value
    return result


def _is_official_chart(raw: dict) -> bool:
    """根据结构自动识别官谱 JSON。"""
    if "BPMList" in raw or "META" in raw:
        return False
    lines = raw.get("judgeLineList")
    if not isinstance(lines, list):
        return False
    if "formatVersion" in raw or "formatversion" in raw:
        return True
    return any(
        isinstance(line, dict)
        and ("notesAbove" in line or "notesBelow" in line or "speedEvents" in line)
        for line in lines
    )


def _official_number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _official_time(value: object) -> int:
    """官谱时间按 int 读取；非整数值按运行时的截断规则处理。"""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _official_time_repr(units: int) -> list[int]:
    """将官谱 T 单位转换为内部可精确表示的 TimeT（1/32 拍）。"""
    integer, remainder = divmod(int(units), 32)
    return [integer, remainder, 32]


def _official_position_x(value: object) -> float:
    """将官谱 Note.positionX（X 单位）比例映射到 RPE 游戏坐标。"""
    return _official_number(value) * OFFICIAL_TO_RPE_X_SCALE


def _official_coord(value: object, *, axis: str, format_version: int) -> float:
    """转换官谱判定线坐标到渲染器的 [-675, 675] 游戏坐标。"""
    raw = _official_number(value)
    if format_version not in (1, 3):
        # 其它版本以画面中心为原点，单位为 0.1H（约 108px）。
        return raw * 108.0
    if format_version == 1:
        span = 880.0 if axis == "x" else 520.0
        raw = raw / span if span else 0.0
    # formatVersion=3 使用左下角归一化坐标；渲染器以中心为原点。
    if format_version == 3:
        raw -= 0.5
    else:
        raw -= 0.5
    return raw * (2.0 * GAME_X_MAX)


def _official_event(
    raw: dict,
    *,
    format_version: int,
    kind: str,
) -> EventData:
    start_t = _official_time(raw.get("startTime", 0))
    end_t = _official_time(raw.get("endTime", start_t))
    start_repr = _official_time_repr(start_t)
    end_repr = _official_time_repr(end_t)
    start = _official_number(raw.get("start", raw.get("value", 0.0)))
    end = _official_number(raw.get("end", raw.get("value", start)))
    if kind == "move":
        if format_version == 1:
            start = int(start) // 1000
            end = int(end) // 1000
        start = _official_coord(start, axis="x", format_version=format_version)
        end = _official_coord(end, axis="x", format_version=format_version)
    elif kind == "move_y":
        if format_version == 1:
            start = _official_number(int(start) % 1000)
            end = _official_number(int(end) % 1000)
        else:
            start = _official_number(raw.get("start2", 0.0))
            end = _official_number(raw.get("end2", 0.0))
        start = _official_coord(start, axis="y", format_version=format_version)
        end = _official_coord(end, axis="y", format_version=format_version)
    elif kind == "speed":
        # 速度事件的 value 单位为 Y/s；当前渲染时间轴只需保留事件数据。
        start = end = _official_number(raw.get("value", 0.0))
    event = EventData(
        bezier=False,
        bezier_points=[0.0, 0.0, 0.0, 0.0],
        easing_left=0.0,
        easing_right=1.0,
        easing_type=1,
        start=start,
        end=end,
        start_time=start_repr,
        end_time=end_repr,
        linkgroup=0,
    )
    # EventData 的拍数由 TimeT 计算，恰好等于 T/32。
    return event


def _parse_official_chart(raw: dict) -> ChartData:
    format_version = int(raw.get("formatVersion", raw.get("formatversion", 0)) or 0)
    raw_lines = raw.get("judgeLineList")
    if not isinstance(raw_lines, list):
        raise ValueError("Official chart judgeLineList must be an array")

    # 以首条有效判定线 BPM 作为统一显示时间轴基准；各线通过 bpm_factor
    # 映射到真实秒时刻，避免不同 BPM 线的 Note 错位。
    line_bpms = [
        _official_number(item.get("bpm"), 0.0)
        for item in raw_lines
        if isinstance(item, dict) and _official_number(item.get("bpm"), 0.0) > 0
    ]
    base_bpm = line_bpms[0] if line_bpms else 120.0
    lines: list[JudgeLineData] = []
    for index, item in enumerate(raw_lines):
        if not isinstance(item, dict):
            item = {}
        bpm = _official_number(item.get("bpm"), base_bpm)
        if bpm <= 0:
            bpm = base_bpm
        notes: list[NoteData] = []
        for collection in (item.get("notesAbove", []), item.get("notesBelow", [])):
            if not isinstance(collection, list):
                continue
            for raw_note in collection:
                if not isinstance(raw_note, dict):
                    continue
                official_type = int(_official_number(raw_note.get("type"), 0))
                if official_type not in (1, 2, 3, 4):
                    continue  # 官谱其它类型表现为不可见、不可判定
                # 官谱: 1 Tap, 2 Drag, 3 Hold, 4 Flick；映射到 RPE 内部编号。
                note_type = {1: 1, 2: 4, 3: 2, 4: 3}[official_type]
                time_t = _official_time(raw_note.get("time", 0))
                hold_t = _official_time(raw_note.get("holdTime", 0))
                end_t = time_t + hold_t if note_type == 2 else time_t
                notes.append(
                    NoteData(
                        type=note_type,
                        start_time_beat=time_t / 32.0,
                        end_time_beat=end_t / 32.0,
                        position_x=_official_position_x(raw_note.get("positionX", 0.0)),
                        raw_start_time=_official_time_repr(time_t),
                        raw_end_time=_official_time_repr(end_t),
                        speed=_official_number(raw_note.get("speed", 1.0), 1.0),
                        floor_position=_official_number(raw_note.get("floorPosition", 0.0)),
                    )
                )

        move_raw = item.get("judgeLineMoveEvents") or []
        rotate_raw = item.get("judgeLineRotateEvents") or []
        alpha_raw = item.get("judgeLineDisappearEvents") or []
        speed_raw = item.get("speedEvents") or []
        move_events = [_official_event(e, format_version=format_version, kind="move") for e in move_raw if isinstance(e, dict)]
        move_y_events = [_official_event(e, format_version=format_version, kind="move_y") for e in move_raw if isinstance(e, dict)]
        rotate_events = [_official_event(e, format_version=format_version, kind="rotate") for e in rotate_raw if isinstance(e, dict)]
        alpha_events = [_official_event(e, format_version=format_version, kind="alpha") for e in alpha_raw if isinstance(e, dict)]
        speed_events = [_official_event(e, format_version=format_version, kind="speed") for e in speed_raw if isinstance(e, dict)]
        move_x_events = sorted(move_events, key=lambda e: e.start_beat)
        layer = EventLayer(
            move_x_events=move_x_events,
            move_y_events=sorted(move_y_events, key=lambda e: e.start_beat),
            rotate_events=sorted(rotate_events, key=lambda e: e.start_beat),
            alpha_events=sorted(alpha_events, key=lambda e: e.start_beat),
            speed_events=sorted(speed_events, key=lambda e: e.start_beat),
        )
        lines.append(
            JudgeLineData(
                name=str(item.get("name", item.get("Name", f"Line {index}"))),
                group=0,
                texture="",
                father=-1,
                z_order=0,
                is_cover=False,
                bpm_factor=base_bpm / bpm,
                notes=notes,
                event_layers=[layer, EventLayer(), EventLayer(), EventLayer()],
                bpm=bpm,
            )
        )

    meta_raw = raw.get("META") if isinstance(raw.get("META"), dict) else {}
    meta = MetaData(
        rpe_version=0,
        background=str(meta_raw.get("background", "")),
        charter=str(meta_raw.get("charter", "")),
        composer=str(meta_raw.get("composer", "")),
        chart_id=str(meta_raw.get("id", "")),
        level=str(meta_raw.get("level", "")),
        name=str(meta_raw.get("name", "")),
        offset=_official_number(raw.get("offset", 0.0)),
        song=str(meta_raw.get("song", "")),
    )
    return ChartData(
        bpm_list=[BPMEvent(base_bpm, [0, 0, 1])],
        meta=meta,
        judge_line_group=[],
        judge_line_list=lines,
        is_official=True,
        format_version=format_version,
    )


def _parse_meta(raw: dict) -> MetaData:
    """解析谱面元信息。"""
    return MetaData(
        rpe_version=int(raw.get("RPEVersion", 0)),
        background=str(raw.get("background", "")),
        charter=str(raw.get("charter", "")),
        composer=str(raw.get("composer", "")),
        chart_id=str(raw.get("id", "")),
        level=str(raw.get("level", "")),
        name=str(raw.get("name", "")),
        offset=int(raw.get("offset", 0)),
        song=str(raw.get("song", "")),
        illustration=str(raw.get("illustration", "")),
        duration=float(raw.get("duration", 0.0)),
    )


def parse_bpm_list(raw_bpm_list: list[dict]) -> list[BPMEvent]:
    """解析 BPM 列表，按 startTime 排序。"""
    events: list[BPMEvent] = []
    for item in raw_bpm_list:
        events.append(
            BPMEvent(
                bpm=float(item["bpm"]),
                start_time=list(item["startTime"]),
            )
        )
    events.sort(key=lambda e: timet_to_beats(e.start_time))
    return events


def _parse_event(raw: dict) -> EventData:
    """解析单个 RPE 事件。"""
    bezier_points = [float(v) for v in raw.get("bezierPoints", [0.0, 0.0, 0.0, 0.0])]
    return EventData(
        bezier=bool(raw.get("bezier", 0)),
        bezier_points=bezier_points,
        easing_left=float(raw.get("easingLeft", 0.0)),
        easing_right=float(raw.get("easingRight", 1.0)),
        easing_type=int(raw.get("easingType", 1)),
        start=float(raw.get("start", 0.0)),
        end=float(raw.get("end", 0.0)),
        start_time=list(raw["startTime"]),
        end_time=list(raw["endTime"]),
        linkgroup=int(raw.get("linkgroup", 0)),
    )


def parse_events(raw_events: list[dict] | None) -> list[EventData]:
    """解析事件列表。"""
    if not raw_events:
        return []
    return [_parse_event(e) for e in raw_events]


def parse_note(raw: dict) -> NoteData | None:
    """解析单个 Note。

    若 isFake=1 则返回 None（假音符仅用于谱面演出，不参与配置预览，见 D2）。
    仅提取 type/startTime/endTime/positionX 四个字段，其余全部丢弃（D1/D3/D4/D5）。

    Raises:
        ValueError: note type 不在 1-4（D12）
    """
    if raw.get("isFake", 0) == 1:
        return None

    note_type = int(raw["type"])
    if note_type not in (NOTE_TAP, NOTE_HOLD, NOTE_FLICK, NOTE_DRAG):
        raise ValueError(f"Invalid note type: {note_type}")  # D12

    raw_start = list(raw["startTime"])
    raw_end = list(raw["endTime"])

    return NoteData(
        type=note_type,
        start_time_beat=timet_to_beats(raw_start),
        end_time_beat=timet_to_beats(raw_end),
        position_x=float(raw.get("positionX", 0)),
        raw_start_time=raw_start,
        raw_end_time=raw_end,
    )


def parse_judge_line(raw: dict) -> JudgeLineData:
    """解析单条判定线。

    - 解析全部 4 个 eventLayers；不足 4 层时用空 EventLayer 补齐
    - extended 字段直接忽略（D7）
    """
    layers: list[EventLayer] = []
    for layer_raw in raw.get("eventLayers", []):
        if layer_raw is None:
            continue  # RPE 允许空事件层以 null 表示（等价于无事件）
        layers.append(
            EventLayer(
                move_x_events=parse_events(layer_raw.get("moveXEvents")),
                move_y_events=parse_events(layer_raw.get("moveYEvents")),
                rotate_events=parse_events(layer_raw.get("rotateEvents")),
                alpha_events=parse_events(layer_raw.get("alphaEvents")),
                speed_events=parse_events(layer_raw.get("speedEvents")),
            )
        )
    # 补齐到 4 层
    while len(layers) < 4:
        layers.append(EventLayer())

    # 解析 notes（过滤 isFake 音符）
    parsed = [parse_note(n) for n in raw.get("notes", [])]
    notes = [n for n in parsed if n is not None]

    bpm_factor = float(raw.get("bpmfactor", 1.0))
    if bpm_factor <= 0:
        raise ValueError(f"bpmfactor must be positive, got {bpm_factor}")

    return JudgeLineData(
        name=str(raw.get("Name", "")),
        group=int(raw.get("Group", 0)),
        texture=str(raw.get("Texture", "")),
        father=int(raw.get("father", -1)),
        z_order=int(raw.get("zOrder", 0)),
        is_cover=bool(raw.get("isCover", 0)),
        bpm_factor=bpm_factor,
        notes=notes,
        event_layers=layers[:4],
        rotate_with_father=bool(raw.get("rotateWithFather", False)),
    )


def _validate_parent_links(lines: list[JudgeLineData]) -> None:
    """校验父线索引并拒绝任意深度的循环嵌套。"""
    count = len(lines)
    for index, line in enumerate(lines):
        if line.father != -1 and not 0 <= line.father < count:
            raise ValueError(
                f"judgeLine[{index}] has invalid father index {line.father}"
            )

    state = [0] * count  # 0=未访问，1=访问中，2=已完成

    def visit(index: int) -> None:
        if state[index] == 1:
            raise ValueError(f"judge line father cycle detected at index {index}")
        if state[index] == 2:
            return
        state[index] = 1
        father = lines[index].father
        if father != -1:
            visit(father)
        state[index] = 2

    for index in range(count):
        visit(index)


def validate_chart(data: ChartData) -> list[str]:
    """验证谱面数据完整性。返回问题描述列表，空列表表示验证通过。

    检查项:
    - BPMList 非空，每个 BPM 事件有有效 startTime 和 bpm > 0
    - META 必要字段存在（name, level, charter, composer）
    - judgeLineList 非空
    - 每条判定线的 eventLayers 长度为 4
    - Note 的 startTime <= endTime（Hold 要求严格小于则给出提示）
    """
    issues: list[str] = []

    if not data.bpm_list:
        issues.append("BPMList is empty")
    for i, bpm_event in enumerate(data.bpm_list):
        try:
            timet_to_beats(tuple(bpm_event.start_time))
        except (ValueError, IndexError) as exc:
            issues.append(f"BPMList[{i}] has invalid startTime: {exc}")
        if bpm_event.bpm <= 0:
            issues.append(f"BPMList[{i}] has non-positive bpm: {bpm_event.bpm}")

    meta = data.meta
    for field_name in ("name", "level", "charter", "composer"):
        if not getattr(meta, field_name):
            issues.append(f"META missing recommended field: {field_name}")

    if not data.judge_line_list:
        issues.append("judgeLineList is empty")

    for line_idx, line in enumerate(data.judge_line_list):
        if len(line.event_layers) != 4:
            issues.append(f"judgeLine[{line_idx}] '{line.name}' does not have 4 event layers")
        if line.bpm_factor <= 0:
            issues.append(
                f"judgeLine[{line_idx}] '{line.name}' has non-positive bpmfactor"
            )
        for note_idx, note in enumerate(line.notes):
            if note.start_time_beat > note.end_time_beat:
                issues.append(
                    f"judgeLine[{line_idx}] '{line.name}' note[{note_idx}]: "
                    f"startTime ({note.start_time_beat}) > endTime ({note.end_time_beat})"
                )
            elif note.type == NOTE_HOLD and note.start_time_beat == note.end_time_beat:
                issues.append(
                    f"judgeLine[{line_idx}] '{line.name}' hold note[{note_idx}] "
                    "has zero duration"
                )

    return issues
