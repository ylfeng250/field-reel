# 外部能力调研

调研日期：2026-10-27。这里只沉淀可复用的方法，不复制第三方代码。

## 采用

- [Herk Edit Kit](https://github.com/nateherkai/herk-edit-kit)：提案与执行分开、保留 EDL、重定时字幕、最终产出 `VERIFY.md`。本项目采用确认闸门、结构化剪辑决策和质检报告。
- [video-agent-skills](https://github.com/Melvynx/video-agent-skills)：自有 B-roll 库用联系表、标签、使用记录管理；异常高内容按各账号自身中位数判断。本项目采用素材库和 `x median` 复盘。
- [video-frames-skill](https://github.com/mugnimaestra/video-frames-skill)：限制抽帧数量、时间戳联系表、按场景抽帧。本项目采用每段 6 帧联系表和成片等距质检帧。
- [video-processing-editing](https://github.com/curiositech/some_claude_skills)：导出前检查颜色、音画同步、重复编码、缩略图候选和质量测量。本项目采用单次正式编码、解码验收和封面候选。
- [FFmpeg 官方文档](https://ffmpeg.org/ffmpeg-all.html)：`blackdetect`、`freezedetect`、`silencedetect`、`ebur128`、`signalstats`。
- [B 站投稿贴士](https://www.bilibili.com/blackboard/activity-1d8l4wx84.html)：封面 1146×716，标签约 4–5 个，封面与内容一致。
- [B 站推荐算法说明](https://www.bilibili.com/blackboard/activity-gPIvOmhxbh.html)：播放、赞、收藏、关注、分享和负反馈都会参与推荐，不把单一点赞率当唯一目标。

## 2026-10-27 的后续核查

[视频技能调研](326b58ca-0ca6-434e-94e4-171df1f56d9e)、[工作流审计](d0b89eef-bbad-48e1-b0f2-96735e665611) 和 [频道经营研究](547d2e95-a1c4-4684-91a4-257d608c44d7) 的结论已经吸收：

- 不安装第二套 FFmpeg、Remotion、YouTube 发布或声音生成技能。
- 素材体检增加可变帧率、HDR 和非常规像素格式提示。
- 每次保存方案都在 `board/decisions/` 留时间戳副本。
- 复盘按发布当天、1 天、3 天、7 天、28 天执行；公开接口没有点击率、完播和留存。
- 封面继续用官方投稿贴士里的 1146×716。如果投稿页显示了不同尺寸，以投稿页为准。

## 没有直接安装

- 通用 FFmpeg 命令表：缺少本账号风格、确认闸门、版权和复盘，安装后反而容易绕过现有流程。
- AI 视频生成、通用 TTS、声音克隆：和「实拍、真实现场」定位冲突，并且用户明确不需要合成配音。
- 依赖 Instagram/TikTok 私有抓取或第三方发布服务的技能：平台不匹配，也会引入账号授权和隐私风险。
- 自动删除静音和口头错误：适合棚拍口播，不适合风声、脚步和真实碎碎念；本项目只把候选放进方案页，由人确认。
- 以 VMAF 比较原片和成片：剪辑成片改变了时长、字幕和画面，不能和原片逐帧对齐；只在同时间线的编码对比实验里使用。

## 实施原则

1. 测量和判断分开：机器报时间点，人看画面决定。
2. 原片永不覆盖：缓存、预览和正式片分目录。
3. 所有自动剪辑都有可读决策文件。
4. 所有投稿都有版权记录和质检报告。
5. 所有运营建议都能回到账号自己的历史数据。

