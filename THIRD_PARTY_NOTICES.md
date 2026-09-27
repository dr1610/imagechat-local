# 出典と条件

- prompts/system_prompt_edit.txt、prompts/system_prompt_t2i.txt: Qwen公式Prompt Rewriteのsystem prompts。今回の包装で本文を変更していません。
  出典: https://github.com/QwenLM/Qwen-Image-2.1/tree/main/prompt_rewrite/prompts
  公式ライセンス原文: licenses/Qwen-RESEARCH-LICENSE.txt
- workflows/: Comfy公式Qwen 2.1テンプレートを参考に、アプリ用のパラメータ・機能宣言・継承形式へ構成した定義。
  参考: https://github.com/Comfy-Org/workflow_templates
- Python、Pillow、ComfyUI、モデルのバイナリは同梱しません。各導入先のライセンスが適用されます。
- ローカル開発版にあった追加Node、第三者ZIP原本、追加LoRA用profilesは含めていません。

公開包装での変更: 製品表示名、独立セットアップ、起動スクリプト、公式モデルを初期選択、追加LoRA方式の対象外化、説明書の再作成。

Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) 2026 Hangzhou Tongyi Laboratory Technology Co., Ltd. All Rights Reserved.
