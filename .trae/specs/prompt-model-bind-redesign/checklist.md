# 提示词-模型绑定关系重构 - Verification Checklist

## 单元级检查点

- [x] Checkpoint 1: `PromptCache.warm_up()` 全局默认识别逻辑已从硬编码 `prompt_code == "Global_Default_Prompt"` 改为 `model_code IS NULL AND is_default=True`
- [x] Checkpoint 2: `PromptCache` 新增了 `_optional_prompts` 字典和 `get_optional_by_code()` 方法，只存 `model_code IS NULL AND is_default=False AND is_enabled=True` 的 prompt
- [x] Checkpoint 3: Repository 层新增了 `is_model_code_bound(session, model_code, exclude_id=None)` 方法，查询条件包含 `is_deleted=False`
- [x] Checkpoint 4: Service 层 `create()` 中，当传入的 `model_code` 非空非 None 时调用 `is_model_code_bound` 校验，冲突抛 400 BusinessException
- [x] Checkpoint 5: Service 层 `update()` 中，当 `model_code` 发生变更且新值非空时同样调用校验（传入 `exclude_id=self.id` 排除自身）
- [x] Checkpoint 6: `_build_identity_system()` 新增了 `extra_prompt` 参数，拼接顺序为：身份 → 全局默认 → 模型绑定 → extra_prompt → user_system
- [x] Checkpoint 7: 去重逻辑实现——追加 content 前与已在 parts 中的每项做字符串全等比较，重复则跳过
- [x] Checkpoint 8: `_load_optional_prompt()` 方法校验了：存在性（未删除）、is_enabled=True、model_code IS NULL、is_default=False；不满足分别返回 404/400 且 message 明确

## 接口级检查点

- [x] Checkpoint 9: `ChatRequest` (非流式 JSON body) 新增了 `prompt_code: Optional[str]` 字段
- [x] Checkpoint 10: `/chat/chat/stream` 流式接口 (Form) 新增了 `prompt_code: Optional[str] = Form(None)` 参数
- [x] Checkpoint 11: 两个对话路由都将 prompt_code 传递到了 dispatcher 对应方法
- [x] Checkpoint 12: dispatcher.chat() 和 chat_stream_with_tools() 方法签名都新增了 `prompt_code: str | None` 参数

## 行为级检查点

- [x] Checkpoint 13: 不传 prompt_code 时 system prompt 拼接结果与改造前等价（全局默认判断逻辑修正除外）
- [x] Checkpoint 14: 传入 prompt_code 对应绑定了模型的 prompt → 返回 400
- [x] Checkpoint 15: 传入 prompt_code 对应全局默认 prompt → 返回 400
- [x] Checkpoint 16: 传入不存在的 prompt_code → 返回 404
- [x] Checkpoint 17: 传入合法 prompt_code → content 出现在模型绑定 prompt 之后、user_system 之前
- [x] Checkpoint 18: 前端指定 prompt content 与已拼接某段完全相同 → 不重复追加
- [x] Checkpoint 19: 软删除的 prompt 占用的 model_code 不阻断新绑定

## 回归检查点

- [x] Checkpoint 20: prompt_cache.refresh() 仍在 create/update/delete 后被调用
- [x] Checkpoint 21: 现有 clear_other_model_defaults / clear_global_default 逻辑未被破坏
- [x] Checkpoint 22: 现有 AI chat_log 记录中 system_prompt 字段能正确记录完整拼接结果
