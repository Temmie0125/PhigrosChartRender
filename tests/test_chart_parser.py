"""chart_parser 单元测试。"""

import json

import pytest

from rpe_render.chart_parser import parse_chart, parse_note, validate_chart


def minimal_raw() -> dict:
    return {
        "BPMList": [{"bpm": 120.0, "startTime": [0, 0, 1]}],
        "META": {
            "RPEVersion": 170,
            "background": "",
            "charter": "t",
            "composer": "c",
            "id": "x",
            "level": "IN 1",
            "name": "n",
            "offset": 0,
            "song": "s",
        },
        "judgeLineGroup": ["Default"],
        "judgeLineList": [
            {
                "Name": "L",
                "notes": [],
                "eventLayers": [
                    {"moveXEvents": [], "moveYEvents": [], "rotateEvents": [], "alphaEvents": [], "speedEvents": []}
                ]
                * 4,
            }
        ],
    }


class TestParseChart:
    def test_parse_valid_chart(self, minimal_chart_path):
        chart = parse_chart(minimal_chart_path)
        assert chart.meta.name == "Minimal Test"
        assert len(chart.bpm_list) == 2
        # BPM 排序
        assert chart.bpm_list[0].bpm == pytest.approx(120.0)
        assert chart.judge_line_list[0].name == "Line1"
        # isFake=1 的音符被过滤 → 剩 2 个
        assert len(chart.judge_line_list[0].notes) == 2

    def test_parse_missing_fields(self, tmp_path):
        for missing in ("BPMList", "META", "judgeLineList"):
            raw = minimal_raw()
            del raw[missing]
            p = tmp_path / "bad.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            with pytest.raises(ValueError, match=missing):
                parse_chart(p)

    def test_parse_empty_bpm_list(self, tmp_path):
        raw = minimal_raw()
        raw["BPMList"] = []
        p = tmp_path / "empty_bpm.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(ValueError, match="BPMList cannot be empty"):
            parse_chart(p)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_chart("no/such/file.json")

    def test_event_layers_fewer_than_4(self, tmp_path):
        raw = minimal_raw()
        raw["judgeLineList"][0]["eventLayers"] = [
            {"moveXEvents": [], "moveYEvents": [], "rotateEvents": [], "alphaEvents": [], "speedEvents": []}
        ]
        p = tmp_path / "few_layers.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        chart = parse_chart(p)
        assert len(chart.judge_line_list[0].event_layers) == 4
        assert validate_chart(chart) == []

    def test_layer_missing_move_x_events(self):
        raw_note_line = {
            "Name": "L",
            "notes": [],
            "eventLayers": [{}, {}, {}, {}],
        }
        from rpe_render.chart_parser import parse_judge_line

        line = parse_judge_line(raw_note_line)
        assert line.event_layers[0].move_x_events == []

    def test_null_event_layer_entries_tolerated(self):
        # 回归：RPE 允许空事件层以 null 表示（真实谱面如 REFLECTION»«REFRACTION
        # 的 eventLayers 为 [层, null, ..., null]），null 层须按空层处理而非报错
        from rpe_render.chart_parser import parse_judge_line

        empty = {
            "moveXEvents": [],
            "moveYEvents": [],
            "rotateEvents": [],
            "alphaEvents": [],
            "speedEvents": [],
        }
        raw_line = {
            "Name": "L",
            "notes": [],
            "eventLayers": [
                {
                    "moveXEvents": [{"start": 0.0, "end": 1.0, "startTime": [0, 0, 1], "endTime": [4, 0, 1]}],
                    "moveYEvents": [],
                    "rotateEvents": [],
                    "alphaEvents": [],
                    "speedEvents": [],
                },
                None,
                empty,
                None,
                None,
            ],
        }
        line = parse_judge_line(raw_line)
        # null 层跳过、不足 4 层补齐 → 恰好 4 层；第 1 层（原索引 2）为空层
        assert len(line.event_layers) == 4
        assert len(line.event_layers[0].move_x_events) == 1
        assert line.event_layers[1].move_x_events == []

    def test_parse_chart_with_null_layer_entries(self, tmp_path):
        # 整图解析路径：5 层含 null（用户谱面实际形态），不崩溃且 4 层补齐
        raw = minimal_raw()
        empty = {
            "moveXEvents": [],
            "moveYEvents": [],
            "rotateEvents": [],
            "alphaEvents": [],
            "speedEvents": [],
        }
        raw["judgeLineList"][0]["eventLayers"] = [empty, None, empty, empty, None]
        p = tmp_path / "null_layers.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        chart = parse_chart(p)
        assert len(chart.judge_line_list[0].event_layers) == 4
        assert validate_chart(chart) == []


class TestParseNote:
    def test_only_required_fields_kept(self):
        note = parse_note(
            {
                "type": 1,
                "startTime": [1, 1, 4],
                "endTime": [1, 1, 4],
                "positionX": 42.5,
                # 应被忽略的字段（D1/D3/D4/D5）
                "above": 2,
                "alpha": 100,
                "size": 3.0,
                "speed": 9.9,
                "visibleTime": 12.0,
                "yOffset": -5,
            }
        )
        assert note is not None
        assert note.type == 1
        assert note.start_time_beat == pytest.approx(1.25)
        assert note.position_x == pytest.approx(42.5)

    def test_is_fake_filtered(self):
        note = parse_note(
            {
                "type": 1,
                "startTime": [0, 0, 1],
                "endTime": [0, 0, 1],
                "positionX": 0.0,
                "isFake": 1,
            }
        )
        assert note is None

    def test_invalid_type_raises(self):  # D12
        with pytest.raises(ValueError, match="Invalid note type"):
            parse_note(
                {
                    "type": 5,
                    "startTime": [0, 0, 1],
                    "endTime": [0, 0, 1],
                    "positionX": 0.0,
                }
            )


class TestParseRealChart:
    def test_real_chart(self, real_chart_path):
        chart = parse_chart(real_chart_path)
        assert chart.meta.name == "Regnaissance"
        total_notes = sum(len(l.notes) for l in chart.judge_line_list)
        assert total_notes > 0
        issues = validate_chart(chart)
        assert issues == []


class TestValidateChart:
    def test_detects_reversed_hold(self, tmp_path):
        raw = minimal_raw()
        raw["judgeLineList"][0]["notes"] = [
            {
                "type": 2,
                "startTime": [8, 0, 1],
                "endTime": [4, 0, 1],
                "positionX": 0.0,
            }
        ]
        p = tmp_path / "rev.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        chart = parse_chart(p)
        issues = validate_chart(chart)
        assert any("startTime" in i and "endTime" in i for i in issues)

    def test_detects_non_positive_bpm(self, tmp_path):
        raw = minimal_raw()
        raw["BPMList"][0]["bpm"] = 0.0
        p = tmp_path / "bpm.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        chart = parse_chart(p)
        issues = validate_chart(chart)
        assert any("non-positive bpm" in i for i in issues)

    def test_detects_missing_meta_field(self, tmp_path):
        raw = minimal_raw()
        del raw["META"]["charter"]
        p = tmp_path / "meta.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        chart = parse_chart(p)
        issues = validate_chart(chart)
        assert any("charter" in i for i in issues)


class TestMultitapFixture:
    def test_raw_timet_preserved(self, multitap_chart_path):
        chart = parse_chart(multitap_chart_path)
        notes = chart.judge_line_list[0].notes
        assert len(notes) == 4
        # 前两个 startTime 分量完全相同
        assert notes[0].raw_start_time == notes[1].raw_start_time == [1, 1, 4]
