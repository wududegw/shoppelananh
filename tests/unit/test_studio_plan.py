import pytest
from pydantic import ValidationError
from agent.api.studio import AdvancedFashionVideoRequest, preview_plan, start_advanced_pipeline
from agent.services.studio_plan import build_scene_plan


def request(**kwargs):
    values = dict(clothing_media_id="garment", subject_mode="child", model_prompt="Mẫu nhí 7–9 tuổi",
                  clothing_prompt="Áo hồng, váy trắng ngắn", location_prompt="Nền pastel sáng",
                  motion_prompt="Vẫy tay, máy quay ngang tầm mắt")
    values.update(kwargs)
    return AdvancedFashionVideoRequest(**values)


@pytest.mark.parametrize("duration", [15, 30, 60])
def test_identity_and_user_directions_reach_every_scene(duration):
    scenes = build_scene_plan(request(duration_seconds=duration))
    assert len(scenes) == duration // 5
    assert scenes[-1]["end_seconds"] == duration
    for scene in scenes:
        for expected in ["Mẫu nhí 7–9 tuổi", "Áo hồng, váy trắng ngắn", "Nền pastel sáng", "ngang tầm mắt"]:
            assert expected in scene["prompt"]
        assert "high fashion pose" not in scene["prompt"]
        assert "Low angle" not in scene["prompt"]


def test_scene_edits_keep_shared_context_and_reference_order():
    scenes = build_scene_plan(request(model_media_id="model", location_media_id="place", scene_actions=["Bước nhẹ", "Mỉm cười", "Vẫy tay"]))
    assert [s["action"] for s in scenes] == ["Bước nhẹ", "Mỉm cười", "Vẫy tay"]
    assert all("Ảnh tham chiếu 3: bối cảnh" in s["prompt"] and "Mẫu nhí 7–9 tuổi" in s["prompt"] for s in scenes)


def test_product_mode_does_not_inherit_model_description():
    text = build_scene_plan(request(subject_mode="product"))[0]["prompt"]
    assert "Mẫu nhí 7–9 tuổi" not in text
    assert "không thêm người mẫu" in text


@pytest.mark.parametrize("actions", [["one"], ["one", "", "three"]])
def test_invalid_edits_rejected_before_submission(actions):
    with pytest.raises(ValueError):
        build_scene_plan(request(scene_actions=actions))


def test_unsupported_duration_is_rejected():
    with pytest.raises(ValidationError):
        request(duration_seconds=16)


@pytest.mark.asyncio
async def test_preview_does_not_submit_generation():
    data = await preview_plan(request())
    assert data["scenes"] == build_scene_plan(request())


@pytest.mark.asyncio
async def test_invalid_plan_does_not_schedule_paid_work():
    from fastapi import BackgroundTasks, HTTPException
    tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        await start_advanced_pipeline(request(scene_actions=["one"]), tasks)
    assert exc.value.status_code == 422
    assert not tasks.tasks
