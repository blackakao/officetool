from ui.pages.branch_list import apply_image_dimensions_to_all_branches


def test_apply_image_dimensions_to_all_branches_preserves_branch_images():
    branches = [
        {
            "custom_fields": {
                "custom_법인인감": {
                    "type": "image",
                    "path": "first.png",
                    "width": 15,
                    "height": 15,
                },
                "custom_기관직인": {
                    "type": "image",
                    "path": "first-stamp.png",
                    "width": 20,
                    "height": 20,
                },
            }
        },
        {
            "custom_fields": {
                "custom_법인인감": {
                    "type": "image",
                    "path": "second.png",
                    "width": 30,
                    "height": 30,
                },
                "custom_기관직인": {
                    "type": "image",
                    "path": "second-stamp.png",
                    "width": 20,
                    "height": 20,
                },
            }
        },
    ]

    apply_image_dimensions_to_all_branches(branches, branches[0])

    second_fields = branches[1]["custom_fields"]
    assert second_fields["custom_법인인감"] == {
        "type": "image",
        "path": "second.png",
        "width": 15,
        "height": 15,
    }
    assert second_fields["custom_기관직인"]["path"] == "second-stamp.png"


def test_apply_image_dimensions_ignores_non_image_values():
    branches = [
        {
            "custom_fields": {
                "custom_전화번호": {"type": "text", "value": "010", "width": 15},
            }
        },
        {
            "custom_fields": {
                "custom_전화번호": {"type": "text", "value": "02", "width": 30},
            }
        },
    ]

    apply_image_dimensions_to_all_branches(branches, branches[0])

    assert branches[1]["custom_fields"]["custom_전화번호"]["width"] == 30
