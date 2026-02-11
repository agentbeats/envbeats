import asyncio
import my_util

from a2a.types import SendMessageSuccessResponse, Message
from a2a.utils import get_text_parts


async def main():
    assessor_url = "http://localhost:9999/"
    assessee_url = "http://localhost:9990/"
    eval_config = {}

    task_text = f"""
Assess the agent(s) located at:
<assessee_url>
{assessee_url}
</assessee_url>
with the following evaluation configuration:
<eval_config>
{eval_config}
</eval_config>
"""
    response = await my_util.send_message(
        assessor_url,
        task_text,
    )
    response_root = response.root
    assert isinstance(response_root, SendMessageSuccessResponse)
    response_result = response_root.result
    assert isinstance(response_result, Message)
    response_text_parts = get_text_parts(response_result.parts)
    assert len(response_text_parts) == 1
    response_text = response_text_parts[0]
    print(f"Evaluation result:\n{response_text}")


if __name__ == "__main__":
    asyncio.run(main())
