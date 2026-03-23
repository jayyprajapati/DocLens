from llm.prompts import format_question
from services.rag_client import query as rag_query


def run(query, user_id, app_name="doclens", doc_id=None, llm_config=None, base_url=None):
    formatted_query = format_question(query)
    result = rag_query(
        query=formatted_query,
        user_id=user_id,
        app_name=app_name,
        doc_id=doc_id,
        llm_config=llm_config,
        base_url=base_url,
    )

    print("\nAnswer:\n")
    print(result.get("answer", ""))

    print("\nSources:\n")
    for i, source in enumerate(result.get("sources", []), start=1):
        section = source.get("section")
        page = source.get("page")
        print(f"[{i}] section={section} page={page}")

    return result


if __name__ == "__main__":
    run(
        query="Who designed the Analytical Engine?",
        user_id="user_a",
        app_name="doclens",
    )
    run(
        query="Who designed the Analytical Engine?",
        user_id="user_b",
        app_name="doclens",
    )
