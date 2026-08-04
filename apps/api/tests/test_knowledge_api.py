"""Knowledge API regression tests."""


def test_delete_knowledge_returns_declared_response(client, auth_supervisor):
    created = client.post(
        "/api/v1/knowledge",
        headers=auth_supervisor,
        json={
            "title": "Delete response regression",
            "category": "experience",
            "content": "Temporary knowledge article.",
        },
    )
    assert created.status_code == 200
    article_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/knowledge/{article_id}",
        headers=auth_supervisor,
    )

    assert deleted.status_code == 200
    assert deleted.json() == {
        "message": "知识条目已删除",
        "id": article_id,
    }

    missing = client.get(
        f"/api/v1/knowledge/{article_id}",
        headers=auth_supervisor,
    )
    assert missing.status_code == 404
