"""RPE JSON 谱面文件的读取、验证与解析为内部数据模型。"""

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

    with open(path, "r", encoding="utf-8") as fp:
        raw = json.load(fp)

    if not isinstance(raw, dict):
        raise ValueError("Top-level JSON must be an object")

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

    return JudgeLineData(
        name=str(raw.get("Name", "")),
        group=int(raw.get("Group", 0)),
        texture=str(raw.get("Texture", "")),
        father=int(raw.get("father", -1)),
        z_order=int(raw.get("zOrder", 0)),
        is_cover=bool(raw.get("isCover", 0)),
        bpm_factor=float(raw.get("bpmfactor", 1.0)),
        notes=notes,
        event_layers=layers[:4],
    )


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
