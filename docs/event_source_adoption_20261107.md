# Juliet 4公演と対象行限定の出典・リンク審査の採用

2026-11-07、運用者から、下記4公演の日程の事実とSTARTO公式リンクの掲載、公演単位の限定policy、出典と公開リンクの独立した確認、公開リポジトリへの反映と本番更新の承認を得た。これはSTARTOから個別の許諾を得たという記録ではない。

公式ページ https://starto.jp/s/p/live/10602 の埋め込み日程を直接取得し、公演名・日付・時刻・会場を保存済み観測と照合した。サイト条件 https://starto.jp/s/p/group/detail/sitepolicy も再確認した。法的な許諾取得や利用可能性を自動判定する仕組みではなく、運用者の掲載判断を既存Gitレビューに記録する。画像・紹介文・チケット説明は今回の4行へ掲載しない。

|日付|開始|会場|固定ID|
|---|---|---|---|
|2026-12-12|18:00|みずほPayPayドーム福岡|evt_607292d730f445068777a2fa76f6e5ea|
|2026-12-13|15:00|みずほPayPayドーム福岡|evt_b9b836e51a7644b7881314070f5e27d5|
|2026-12-19|17:00|バンテリンドームナゴヤ|evt_8532bb80a4ff45748eadb55423d3c06b|
|2026-12-20|15:00|バンテリンドームナゴヤ|evt_59aa527ee44a46928b8ed82a4134aef5|

取得元と公開URLの選択は、実際のSTARTO観測 `starto_concert / artist_official` を使用する。取得できていない会場本文を確認済みとして扱わない。対象4件だけを固定ID・観測fingerprint・source record・日時・会場・公演名・URLへ結合し、STARTOドメイン全体や他の公演の公開判断は変更しない。

## 同世代入力と移行範囲

準備時のproducer mainは `1984a9e46210753ed9b2110c44ba43eb073ce6f5`、consumer mainは `46019a8eb38ae86b3896cb4a8fe457863a2d6996`。Release ID 290199455の全7ファイルをAPI digestと照合した。SQLiteはeventsが `d2146a3bb818ab675f87bbdbc5b75a53973933470114f15d8a95b21e2275fd7a`、signalsが `de82b6d95480aeee7eee27707ab991c0f7fc5caa7f349cdfb99a902d71b65c2a` で、両方とも変更しない。

実台帳revision 51の全既存events/relationsを保ち、隔離で一度作成した同じ4 IDをrevision 52として採用する。新規登録コマンドを本番で再実行して採り直さない。未公開の仮evidenceを、今回の直接照合と運用者の掲載判断へ置き換え、実要求のcanonical hashに結び付けた。元の51世代の履歴は変更していない。

最新実公開の全期間1104行からv5 bootstrap baselineを生成し、明示した4 IDだけを追加した1108行の採用baselineを使用する。既存の公開行・source signatureは引き継ぎ、未確認の現在DBを一律に承認し直さない。通常LPは992→996行、全期間は1104→1108行で、既存行の全項目は一致した。生成日時・固定ID台帳metadata・数値集計は新しい生成世代を表す。

移行対象はコード・回帰試験・運用文書と、`event_identity_registry.json`、`reviewed_event_sources.json`、`reviewed_event_baseline.json`、`lp_events.json`、利用側4件scopeおよび実Releaseから作る公開候補・既存再採用履歴である。全期間LPとmanifestは採用commitから既存Release workflowが生成する。合成DB、架空公演、注入URL、private preview、過去のSIMULATED要求・manifestは配布しない。

## 定時更新と保留

通常・rebase後の再生成・全期間生成は、同じGit管理のmap/baselineを使う。map/baselineは一組が必須。新規固定IDが未確認の場合は該当行を保留し、他の正常な更新を継続する。4収集元の確認経路を回帰試験している。

既存IDの未確認本文・補助情報・URL変更は、同じidentityで現在のactive観測に結び付く旧公開行を全項目保持し、変更候補だけ保留する。新しい未確認本文・URLを上流LPへ出さない。壊れたmap/baseline、安全に結合できないidentity変更、非空WAL、生成中の入力変更は停止する。取消・消えた候補をbaselineから復活させない。URLの取得元、公演リンク、補助URLをそれぞれ検査し、新規・明示変更行だけ公開項目を限定する。

保留件数はActions warningとStep Summaryへ出る。既存pending CLIで詳細をprivate出力へ生成できる。無条件の新規採用、独自認証や審査journalの新設はしない。保持期間の自動期限や上限は設けておらず、保留解消はGitレビューで行う。baseline拡張も定時処理では自動実行しない。4件をbaselineへ入れた後はpublicationをpendingへ変えるだけでは撤回できないため、訂正・撤回は明示レビューで履歴を進める。

## 配布と復旧

producer反映後、実commitを参照するReleaseの6資産とmanifestを再取得・検証してからconsumer候補を作る。利用側は既存の再採用処理を使い、旧runtime・新候補・旧/new policy・保存日程・不変historyを照合する。既存runtime全行と保存日程を保持し、4 IDだけを追加する。保存日程の差分が空でも、通常公演4件は候補全体とpolicyのSHAで結び付く。

復旧は `event_publication_recovery.md` とSideBizの既存 `docs/operations/publication-recovery.md` に従う。正常Release7ファイルを置換前に確保し、同世代の一式を再送してmanifestを最後に置く。ID台帳や新しい不変履歴は巻き戻さず、再採番しない。公開JSON・ページ・policy・保存日程を一式でforward復元し、無関係な記事や鮮度項目は保持する。

Git・Release・両リポジトリの公開は一括atomicではない。基準SHAや入力hashが変わったら古い候補をそのまま反映せず再確認する。実公開の成否はcommit/pushだけで判断せず、Release、Actions、公開JSONとページを読み戻して確認する。
