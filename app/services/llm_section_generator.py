"""
复盘长文章节与主提示词：正文结构定义于 `config.replay_prompt_templates`。
（历史文件名兼容：部分需求文档称「llm_section_generator」。）
"""

from config.replay_prompt_templates import MAIN_REPLAY_PROMPT, build_main_replay_prompt

__all__ = ["MAIN_REPLAY_PROMPT", "build_main_replay_prompt"]
