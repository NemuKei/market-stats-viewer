# AGENTS.md

## Purpose

このファイルは「新規リポジトリにもそのまま流用できる」運用テンプレート。
正本優先・最小読込・最小差分で、事故を減らしつつ実装とドキュメント更新を進める。
賢く進めることと、危険な変更を通さないことの両立を優先する。

## Scope

- このファイル単体で運用を開始できることを優先する。
- 外部リポジトリや親ワークスペースへの参照は任意。存在しなくても止めない。

## Read Budget

- 初手で読むのは `AGENTS.md` のみ。
- 追加読込は、タスク遂行に必要な最小数に限定する（目安: 追加2ファイルまで）。
- 不足があれば推測せず、必要ファイルを特定して読む。
- サブエージェント利用時も read budget を免除しない。起動時に対象ファイルと理由を固定し、読み広げが必要になった場合はメインスレッド側へ戻して再判断する。

## Task Read (Only When Needed)

- 仕様変更/挙動確認: 対象領域の `spec_*.md` など
- 現在地の確認: `STATUS.md` 相当
- 判断理由の確認: `DECISIONS.md` 相当
- 実装規約の確認: `README.md` 相当
- リポジトリ固有運用: `Local Extension` で定義されたドキュメントのみ参照

## Skills (Only When Needed)

- root `AGENTS.md` は repo-wide の常時ルールを定義し、Skill は必要時に task-specific procedure だけを追加する。
- 常時ルールや設計原則を Skill へ重複展開しない。Skill 側で不足する repo-wide 判断は root `AGENTS.md` を参照する。
- 新規 Skill 名は hyphen-case を既定とする。既存の underscore 名は専用 migration まで legacy として扱い、rename を他タスクへ混ぜない。
- `.agents/skills/README.md` には、この repo 固有 Skill だけを残す。
- `context-writeback`: 常設コンテキストへの反映が必要なときだけ使う。共有 Skill として `~/.codex/skills` から使う。
- `second-brain-capture`: Codex 作業のうち、repo をまたいで再利用する価値がある情報を Obsidian SecondBrain vault へ記録または更新するときだけ使う。共有 Skill として `~/.codex/skills` から使う。
- `design-review`: 設計相談や大きめ変更で、責務境界・依存方向・分割要否を点検したいときだけ使う。共有 Skill として `~/.codex/skills` から使う。
- `docs-governance`: ドキュメント新設/統合/正本反映の判断が必要なときだけ使う。共有 Skill として `~/.codex/skills` から使う。
- `intent-governance`: 複数の仕様判断にまたがって再利用する判断原則を `INTENT.md` 相当へ反映するときだけ使う。共有 Skill として `~/.codex/skills` から使う。
- `spec-governance`: タスクが `spec` 更新に影響するかを判定し、実装開始前の checkpoint で `spec` を更新する必要があるときだけ使う。共有 Skill として `~/.codex/skills` から使う。
- `repo-bootstrap`: 新規リポジトリの最小構成を責務ベースで整備するときだけ使う。共有 Skill として `~/.codex/skills` から使う。
- `release-gate`: リリース可否判定、タグ提案、リリースノート作成、タグ付け実行を標準化したいときに使う。共有 Skill として `~/.codex/skills` から使う。
- `task-add-and-triage`: 新規タスク追加後に実装粒度チェック（必要時は子タスク分割）と棚卸し/統合効率化/順番最適化を同一ターンで行いたいときに使う。共有 Skill として `~/.codex/skills` から使う。
- `verification-before-completion`: 成功/完了を主張する前に fresh verification を必ず取りたいときに使う。共有 Skill として `~/.codex/skills` から使う。
- `gitignore-guard`: 新規作成・生成されたファイルを `.gitignore` へ入れるべきか判定するときだけ使う。共有 Skill として `~/.codex/skills` から使う。
- `search-first`: 実装前に既存解・外部ライブラリ・既存パターンを先に調べたいときに使う。共有 Skill として `~/.codex/skills` から使う。
- `missing-capability-proposal`: 実行中または verify 中に未導入のツール、ライブラリ、Skill、preset が不足能力の原因になったときに、導入提案の要否を短く整理したいときに使う。共有 Skill として `~/.codex/skills` から使う。
- `deep-research`: 複数ソースの比較、出典付きの調査要約、論点整理が必要なときに使う。共有 Skill として `~/.codex/skills` から使う。
- `thread-contract-handoff`: スレッド開始時に目的・範囲・終了条件を固定し、終了時に handoff 要否をユーザー確認で決めたいときに使う。共有 Skill として `~/.codex/skills` から使う。
- `create-cli`: 新しい CLI、サブコマンド、引数体系、出力契約を設計または変更するときに使う。共有 Skill として `~/.codex/skills` から使う。
- `bom-guard`: Windows 環境で UTF-8 BOM の混入防止や除去が必要なときに使う。共有 Skill として `~/.codex/skills` から使う。
- `dictionary_maintenance`: `event_signals` の artist/venue 辞書をメンテするときだけ使う。手順は `.agents/skills/dictionary_maintenance/SKILL.md` を参照。
- `generic-skill-template-sync`: repo 固有 skill を汎用化できるか判定し、template へ逆輸入するか整理するときに使う。手順は `.agents/skills/generic-skill-template-sync/SKILL.md` を参照。
- `spec-wallbat-to-task`: 仕様追加・修正の相談で壁打ちを先行し、仕様確定後にタスク化してから実装へ進めるときに使う。手順は `.agents/skills/spec-wallbat-to-task/SKILL.md` を参照。

## Archive

- `archive/**`, `thread_logs/**`, `handovers/**` は参照専用
- 新規ルールは archive に追加しない

## Source Priority

1. セキュリティ/法令/公開制約
2. 仕様書（`spec_*.md` など）
3. 現況/意思決定ログ（`STATUS` / `DECISIONS`）
4. `AGENTS.md`
5. Archive

同順位で矛盾した場合は、より新しい決定を優先する。
未解決なら `DECISIONS` 相当へ `D-YYYYMM-xxx` 形式で暫定記録して進める。

## Constant Context Rules

- 推測禁止。条件を満たすときだけ `context-writeback` の手順で常設コンテキストへ反映する。

## Obsidian SecondBrain Capture

### Purpose

各 repo での Codex 作業のうち、次回以降も参照する価値がある情報は、Obsidian SecondBrain vault へ記録する。

Obsidian vault:

```text
C:\Users\n-kei\Documents\Obsidian\SecondBrain
```

### Source Of Truth

この repo の仕様、進捗、決定、タスクの正本は repo 内ドキュメントである。

Obsidian は、repo をまたいで検索、比較、再利用するための横断索引と、Codex の作業文脈を維持するための補助情報である。

repo 内正本と Obsidian が矛盾する場合は、repo 内正本を優先する。

### System Notes

SecondBrain 全体の目的、保守、repo 連携、別端末再現は vault 内の次の system note を正本として扱う。

- `99_System/SecondBrain Charter.md`
- `99_System/SecondBrain Operations.md`
- `99_System/SecondBrain Repo Integration Rule.md`
- `99_System/SecondBrain Device Setup and Recovery.md`

### Reuse Checkpoint

作業開始時は、まず対象 repo の `STATUS`、`DECISIONS`、`tasks_backlog`、`spec`、root `AGENTS.md` と Codex memory を確認する。

SecondBrain は、単一 repo 内の現在地管理を置き換えない。repo 内 docs と memory で十分に閉じる実装、修正、検証では、SecondBrain を無理に検索しない。

次の条件に該当する場合は、SecondBrain を検索する。

- 他 repo の判断、実装、失敗した方法、検証コマンドを今回の repo に応用する可能性がある。
- レベニューマネジメント、ホテル、需要予測、価格、競合調査について、repo 内 docs だけでは足りない横断知識や外部知識が必要である。
- 論文、外部資料、Deep Research、専門用語、開発概念を確認する必要がある。
- AGENTS.md、Skill、automation、SecondBrain、別端末運用など、repo をまたぐ運用ルールに関係する。
- ユーザーが「前に決めた」「知識体系」「単語帳」「論文」「他 repo でも」「別端末でも」といった継続文脈を示した。

検索対象は `20_Areas/`、`30_References/`、`00_Inbox/Codex Captures/`、`99_System/`、`99_System/Bases/` を優先する。

SecondBrain を参照した場合でも、repo 内 `STATUS`、`DECISIONS`、`tasks_backlog`、`spec`、root `AGENTS.md` を正本として優先する。参照した note が今回の判断に影響する場合は、作業メモまたは最終報告で短く示す。参照しなかった場合でも、repo 内正本で閉じる作業なら問題として扱わない。

### Capture Triggers

次の作業を行った場合、終了前に Obsidian への記録対象を判断する。

- 非自明な実装、調査、設計判断、docs handoff
- 次スレッドの再開地点が重要な作業
- repo をまたいで再利用できる判断、検証方法、失敗知識
- ユーザーの説明粒度、確認頻度、委任範囲に関する作業認識の更新
- `AGENTS.md`、Skill、handoff、automation、Obsidian vault 運用の変更
- ユーザー向けに噛み砕いて残す価値がある論文、外部知識、開発概念、専門用語
- 今後の開発判断に使えそうな補助メモ

### Completion Checkpoint

次のいずれかを行った場合、最終回答の前に `capture-needed: yes | no` を明示的に判定する。

- 非自明な実装、調査、設計判断、docs 更新、handoff
- AGENTS.md、Skill、automation、Obsidian vault 運用の変更
- 論文、外部知識、開発概念、専門用語に関する整理
- repo をまたいで再利用できる判断、検証方法、失敗知識の発見

`capture-needed: yes` の場合は、`second-brain-capture` Skill を使い、repo 内正本と Obsidian note の境界を分けて記録する。

`capture-needed: no` の場合は、保存しない理由を短く示す。例: 単発回答、repo 内正本に十分記録済み、再利用価値がない、秘密情報を含むため保存しない。

この判定を省略したまま、非自明な作業を完了扱いにしない。

### Git Sync Checkpoint

SecondBrain vault は複数端末から更新される前提で扱う。Codex が SecondBrain の note、system file、Base、Canvas を作成または更新した場合、既定の完了状態は、関係する変更だけを commit し、active branch を `origin` へ push し、`git status --short --branch` で未コミット差分がなく remote と同期していることを確認した状態である。

stage するのは現在 task に関係する vault 変更だけにする。Obsidian の local UI state、cache、plugin token、sync config、内容未確認のユーザー作成 note は stage しない。秘密情報混入の疑い、未完成 note、内容未確認のユーザー作成 note、git 失敗のいずれかで push できない場合は、最終報告で理由、残っている差分、remote との同期状態を明記する。
### Capture Rules

- 新規作業記録は `00_Inbox/Codex Captures/` に作成する。
- note には `audience`、`update_mode`、`confidence` を入れる。
- `audience: codex` の note は、Codex が次回以降の作業文脈として使う。
- `audience: user` の note は、ユーザー本人が後で読む知識体系として扱う。
- `audience: shared` の note は、Codex とユーザーの両方が参照する運用ルールや判断基準として扱う。
- Codex 側の作業プロファイルは `update_mode: automatic` として自動更新してよい。
- 誤りが後続のやり取りで見つかった場合は、必要に応じて `Revision Notes` に修正理由を残す。
- ユーザー向け知識 note は日本語で噛み砕き、英語の正式名称、略語、検索語、論文タイトル、API 名、ライブラリ名は保持する。
- 専門用語、略語、モデル名、評価指標、データ概念、設計概念、業務概念は glossary note または candidate queue へ接続する。
- ユーザー向け note に書くと冗長だが今後の開発に応用できる補助メモは、Codex Application Memos へ分ける。
- Glossary note と論文 note は、Obsidian Bases の一覧に出るように必要な frontmatter property を埋める。
- 未確認、出典確認、開発応用の棚卸しは Knowledge Dashboard と review 系 Base から辿れるようにする。

### Do Not Capture

- API key、Cookie、token、認証情報
- 不必要な個人情報
- 一時ログ全文
- repo 内正本と矛盾する未確認情報
- 人格評価、感情の断定、開発支援に不要な推測

### Subagent Orchestration

SecondBrain 更新が非自明な場合は、subagent 利用を標準候補にする。

メインスレッドが担うこと:

- 保存先、`audience`、`update_mode`、`confidence` の最終判断
- repo 内正本と Obsidian note の境界判断
- subagent 結果の統合
- 最終差分、verify、commit、push、最終報告

subagent に委譲してよいこと:

- 既存 note の探索
- 関連 glossary 候補の抽出
- 論文や外部資料の source、DOI、Open Access 状態の確認
- ユーザー向け説明と Codex 向けメモの分離案作成
- frontmatter、wikilink、秘密情報、repo 正本混同のレビュー

同じファイルを複数 agent が同時に編集する作業、repo 正本か Obsidian note かの最終判断、commit、push、最終報告はメインスレッドが担う。

### Knowledge Note Rules

ユーザー向け知識体系は、日本語で読める説明を基本にする。

英語の正式名称、略語、検索語、論文タイトル、API 名、ライブラリ名、モデル名、評価指標は、後から公式資料、論文、実装へ接続するために残す。

Glossary note は `99_System/Bases/Glossary.base`、論文 note は `99_System/Bases/Academic Papers.base` に表示される property を埋める。未確認、出典確認、開発応用は `20_Areas/Knowledge Dashboard.md`、`99_System/Bases/Knowledge Review Queue.base`、`99_System/Bases/Source Access Review.base`、`99_System/Bases/Development Application.base` から辿れるようにする。Base file は一覧の定義であり、知識の本体は個別 Markdown note に残す。

初出では、可能な限り次の形を使う。

```text
日本語での理解（English formal name、略語）
```

### Skill

Obsidian capture を作成または更新する場合は、`second-brain-capture` Skill を使う。

## Docs Governance

- 重複記載を避け、会話は正本にしない。正本反映の判断は `docs-governance` の手順に従う。

## Engineering Defaults

- デフォルトは単純さを優先する（YAGNI / KISS / DRY）。後方互換の shim・fallback は、明確な運用要件がある場合のみ追加し、目的・適用範囲・廃止条件を記載する。
- 実行中または verify 中に、未導入のツール、ライブラリ、Skill、preset が不足能力の原因になっている場合は、短い導入提案をしてよい。提案すべきか迷う場合は、提案を抑えるより、不足内容と候補を短く示す方を優先する。
- 新しい外部ツールや依存ライブラリを提案する前に、既存手段で代替できないか確認する。外部導入候補が残る場合は、`security-best-practices` が使える環境ではそれを使い、使えない場合でも供給網、権限、install script、version 固定を確認する。
- 導入提案を見送られた場合は、少なくとも `not-now`、`policy-reject`、`security-reject`、`cost-reject` のいずれかで理由を整理する。`policy-reject` と `security-reject` は、明示的な再検討があるまで再提案しない。
- ビジネスルールは UI / CLI / handler / transport 層へ直置きせず、責務が明確な層へ寄せる。
- 外部 API / DB / file I/O などの副作用は境界に隔離し、ドメイン判断と混在させない。
- 新規コードは継承より composition を優先し、interface / abstraction は現実の差し替え点またはテスト上の必要がある場合に限る。
- god file / god class / god function を拡張しない。責務が増える変更は先に分割方針を示す。
- 既存の密結合構造を無批判に踏襲しない。変更が責務境界をまたぐ場合は、置き場所と依存方向を先に点検する。
- テストしやすい単位を優先し、副作用は端に寄せる。既存の公開挙動は、タスクが明示的に変更を求めない限り保持する。
- Git は `main` 一本を既定とし、branch / worktree は前提にしない。AI は rebase / force push / 履歴整理を勝手にしない。
- 変更は最小差分・1タスク1コミットを原則とする。verify 前の保存が必要なときだけ `WIP:` 一時コミットを許可する。
- 変更予算を超えて一度に広く触らない。差分が大きい、横断的、または危険操作が混ざる場合は停止し、分割案を先に示す。
- 3ステップ以上、または責務境界・仕様判断を含むタスクでは、実装前に `変更範囲`、`保持すべき公開挙動`、`最小 verify` を先に明示する。
- 実装中に前提、影響範囲、または verify 方法が崩れた場合は、そのまま押し切らず、分割または再計画へ戻す。
- 明示承認なしで行わない: 依存追加/更新、rename / move / 大量削除、設定変更、DB / migration、認証 / secrets / 権限、sample / raw データ変更。
- verify 失敗時の自己修正は最大2回。解消しなければ停止し、失敗内容・原因仮説・未解決点・次に見る箇所だけ報告する。

## Directory Guideline

- 責務ベースで構成し、入口はルート `AGENTS.md` とする。`START_HERE.md` / `THREAD_START.md` は常設しない。詳細は `repo-bootstrap` を参照。

## Local Extension (Optional)

この節はリポジトリ固有ルールを置く任意領域。未記載でも運用可能。

### 運用計画の参照先

- 運用計画や次アクションの確認は `docs/context/STATUS.md` を参照する。

### Repo-specific Domain Rules

- データ取得元は公的公開統計を原則とする。
- 仕様外の挙動は既存仕様として断定せず、新仕様提案として扱う。
- 既存仕様の変更時は `docs/context/DECISIONS.md` を更新し、関連する `docs/spec_*.md` に反映する。
- 市場統計またはイベント情報に関わる実装では、LP側で利用するデータへの影響を必ず確認する。対象は `data/market_stats.sqlite`、`data/events.sqlite`、`data/event_signals.sqlite`、`data/manifest.json`、Release asset、関連workflow、表示用のカテゴリ・期間・集計・正規化ロジックを含む。影響がない場合も、理由を `lp_impact=none` 相当として説明する。
- `.agents/skills/` には、この repo 固有の Skill だけを置く。
- 共有 Skill は `~/.codex/skills` から使い、この repo へ複製しない。

### Subagent Policy

- メインスレッド側は全体判断・統合・verify・最終報告を担う。クリティカルパスの実装も既定ではメインスレッド側が担当し、明確に独立した変更範囲だけをサブエージェントへ委譲する。
- 役割定義ファイルの正本は `C:\Users\n-kei\.codex\agents\*.toml` とし、この節は呼称と委譲境界のみを定義する。
- repo 側の `.codex/agents/*.toml` は、この repo だけで追加設定や上書きが必要な場合に限って使う。
- `.codex/agents/*.toml` では `name` を識別子の正本とする。`subagent://...` で参照する値と、生成時に Codex が使う役割識別子は `name` を基準に解釈する。
- `researcher` は read-only の調査担当。コードパス、関連テスト、影響範囲、関連ドキュメントの特定だけを行い、編集や広い設計変更を既定にしない。
- `implementer` は限定実装担当。割り当てられたファイル/責務だけを編集し、他担当と write set を重ねない。
- `reviewer` は read-only のレビュー担当。方法的懐疑の立場で、正しさ・回帰・テスト不足・前提崩れを優先して指摘する。
- `docs_curator` は docs 担当。`docs/tasks_backlog.md` / `docs/context/STATUS.md` / `docs/context/DECISIONS.md` / `spec_*.md` の正本配置、重複排除、反映順の判断を担う。
- タスクに直結する最小 docs 更新は実装担当またはメインスレッド側が行う。`docs_curator` へ引き継ぐのは、正本の置き場判断、`spec_*.md` 反映要否、backlog triage、archive/release 連動判断が必要な場合に限る。
- project-scoped の `.codex/` はローカル状態を含み得るため丸ごと追跡しない。既定では `.codex/config.toml` だけを version 管理する。
- サブエージェントの既定は未使用とする。ただし、main thread の文脈保護に資する bounded delegation であり、対象範囲・返却形式・寿命を事前に固定できる場合に限って使用できる。
- サブエージェントへ優先して委譲するのは、調査、影響範囲確認、テスト切り分け、レビュー、要約などの read-heavy な作業とする。write-heavy、横断変更、クリティカルパス、高判断コスト変更は既定でメインスレッド側に残す。
- 実装を委譲する場合は write set を明示し、同一ファイル、同一責務、共有設定、同一 verify 対象を複数担当へ重ねて割り当てない。競合が見込まれる変更はメインスレッド側へ戻す。
- サブエージェントによる調査用テストや部分検証は許容するが、最終 verify 判定はメインスレッド側だけが行う。最終判断、commit / push、依存追加/更新、設定変更、DB / migration、外部接続変更、正本ドキュメント反映要否の判断もメインスレッド側が保持する。
- サブエージェントは短命・単機能を原則とし、1タスク1目的の使い捨てを基本とする。同一 thread の継続利用は、同一 bounded scope を維持できる場合に限る。
- サブエージェントの返却は生ログではなく蒸留要約とし、最低限 `結論`、`根拠ファイル`、`不確実点`、`推奨次アクション`、`編集ファイル一覧`、`verify 実施有無` を含める。

## Owner Profile (Stable Context)

- Language: 日本語
- Domain baseline: 対象ドメインの実務知識あり
- Technical baseline: 非エンジニア。コード全文より「何を/なぜ/影響範囲」を先に把握したい
- Communication preference: 結論先出し + 次アクション明確 + 専門語は必要最小限
- Explanation depth: 実装意図と変更点の説明を重視

更新ルール:

- 本人が明示した内容のみ更新する（推測禁止）
- 同傾向が複数セッションで再現したときに固定化する
- 更新時は `DECISIONS.md` 相当に `D-YYYYMM-xxx` で1件記録する

## Delivery Rule

- 最終報告はコード詳細より「何を変えたか / なぜ変えたか / 影響範囲 / GUI確認要否」を優先する。
- サブエージェントを使った場合も、最終報告はメインスレッド側が統合し、owner 向けに「何を / なぜ / 影響範囲」を先に示す。サブエージェントの生ログや中間試行は最終報告へ持ち込まない。
- GUI/UXに影響する実装を行った場合、最終回答に `GUIで確認してほしい箇所` を必ず明示する。
- `GUIで確認してほしい箇所` には、画面名・操作手順・期待結果を最低1件以上含める。
- GUI確認が不要な変更（内部処理/ドキュメントのみ等）の場合は、最終回答に `GUI確認不要` と理由を明記する。
- verify 未通過では通常の commit / push を行わない。Codex がセッション中に意味のある差分を作った場合、ユーザーが停止を明示しない限り、verify 通過後は commit と `origin/main` への push までを既定の完了状態とする。verify 手段が未整備なら勝手に増やさず、その旨を報告する。

## Short Command Defaults

ユーザーの短い指示は、追加説明を要求せずに次の既定動作へ展開する。

- `すすめて`: `STATUS.md` の現在の task bundle と `tasks_backlog` の優先順位を確認し、完了済み task を再開せず、次の 1 task を進める。実装を伴う場合は verify、関連 docs 同期、Session Git Sync Gate まで進める。
- `次にすすめて`: 現在の task が完了済みであることを確認し、`STATUS.md` または `tasks_backlog` に明記された次 task へ移る。完了済み task の追加掘り下げを既定にしない。
- `Docs整備して`: docs-only として扱う。実装ファイルを編集せず、`STATUS.md`、`tasks_backlog`、`DECISIONS.md`、関連 `spec` の整合性を確認し、次スレッド入口、非対象、完了条件を明記する。
- `スレッド移行して`: 次スレッドが会話履歴を読まなくても再開できるように、最初に読む正本、次の 1 task、非対象、終了条件、verify / commit 状態を `STATUS.md` などの正本へ残す。
- `見解だけ`: read-only として扱う。実装、commit、push をしない。必要な現物確認は行い、結論、根拠、不確実性、実装するなら最初に確認する事項を分けて報告する。
- `Pushまでしておいて`: 通常の追加要件ではなく、Session Git Sync Gate の実行漏れを補正する指示として扱う。この指示がなくても、意味のある差分があり条件を満たす場合は commit / push まで行う。

## Session Git Sync Gate

Codex がセッション中に意味のある差分を作った場合、ユーザーが停止を明示していない限り、既定の完了状態は次のすべてを満たす状態である。

1. 変更内容に対応する verify が通っている。
2. 必要な docs、`STATUS.md`、`tasks_backlog`、`DECISIONS.md`、関連 `spec` が同期されている。
3. 現在 task に関係する差分だけが stage されている。
4. active branch が `main` である。
5. commit が作成されている。
6. commit が `origin/main` へ push されている。
7. push 後に `git status --short --branch` を再確認し、未コミット差分なし、remote と同期済みであることを確認している。

次の場合は commit / push しない。

- verify が失敗している。
- 秘密情報、個人情報、生成キャッシュ、巨大な一時ファイルの混入疑いがある。
- ユーザー由来の無関係差分が同じファイルまたは同じ working tree に残っており、現在 task の差分だけを安全に stage できない。
- 仕様判断、release 判断、公開判断、削除判断など、ユーザー判断待ちの項目が残っている。
- no-op で、repo に意味のある差分がない。
- ユーザーが `commitしない`、`pushしない`、`見解だけ`、`docs案だけ` など、保存しない意図を明示している。

commit / push しない場合は、最終報告で理由、残っている差分、未実施または失敗した verify、次に必要な判断を明記する。
