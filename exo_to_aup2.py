"""
exo_to_aup2.py
AviUtl (.exo) -> AviUtl2 (.aup2) 変換プロトタイプ

現時点で対応しているフィルタ:
  - テキスト
  - 標準描画
  - 色ずれ

対応表は実際にAviUtlとAviUtl2で同じオブジェクトを作って
出力を見比べて作った手作りのものです。推測で埋めた部分には
コメントで「要検証」と書いています。未対応のフィルタは、
変換せずスキップして警告だけ出します(黙って落とすより安全)。

使い方:
    python exo_to_aup2.py 入力.exo [出力.aup2]
"""

import re
import sys
from pathlib import Path


# ------------------------------------------------------------
# 1. .exo パーサー
#    .exo は Shift-JIS でエンコードされた INI 風のテキストファイル
# ------------------------------------------------------------

def parse_exo(path: Path) -> dict:
    """.exo を読み込み、{セクション名: {キー: 値}} の辞書にする"""
    text = path.read_text(encoding="shift_jis", errors="replace")

    sections: dict[str, dict[str, str]] = {}
    current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if not line:
            continue

        header = re.match(r"^\[(.+)\]$", line)
        if header:
            current = header.group(1)
            sections[current] = {}
            continue

        if current is None:
            # セクションが始まる前の行は無視
            continue

        if "=" in line:
            key, _, value = line.partition("=")
            sections[current][key] = value

    return sections


# ------------------------------------------------------------
# 2. text= の特殊デコード
#    UTF-16LE のバイト列を16進文字列にしたものなので、
#    16進 -> バイト列 -> UTF-16LEデコード、の順で戻す
# ------------------------------------------------------------

def decode_exo_text(hex_str: str) -> str:
    hex_str = hex_str.strip()
    # 奇数長になることがあるので保険で揃える
    if len(hex_str) % 2 != 0:
        hex_str = hex_str[:-1]
    try:
        raw = bytes.fromhex(hex_str)
        text = raw.decode("utf-16-le", errors="ignore")
        return text.rstrip("\x00")
    except ValueError:
        return ""


# ------------------------------------------------------------
# 3. フィルタ変換ルール
#    exoのキー名 -> aup2のキー名(必要なら値変換関数も)
# ------------------------------------------------------------

def conv_align(value: str) -> str:
    # 0-8: 横書き(左/中央/右寄せ × 上/中/下)
    # 9-17: 縦書き(縦書 上寄/中央/下寄 × 右/中/左)
    # 6以降はAviUtl2側の一覧表示順からの推定。6か9あたりは実機で要検算
    table = {
        "0": "左寄せ[上]",
        "1": "中央揃え[上]",
        "2": "右寄せ[上]",
        "3": "左寄せ[中]",
        "4": "中央揃え[中]",
        "5": "右寄せ[中]",
        "6": "左寄せ[下]",
        "7": "中央揃え[下]",
        "8": "右寄せ[下]",
        "9": "縦書 上寄[右]",
        "10": "縦書 中央[右]",
        "11": "縦書 下寄[右]",
        "12": "縦書 上寄[中]",
        "13": "縦書 中央[中]",
        "14": "縦書 下寄[中]",
        "15": "縦書 上寄[左]",
        "16": "縦書 中央[左]",
        "17": "縦書 下寄[左]",
    }
    return table.get(value, value)


def conv_text_type(value: str) -> str:
    # lua.txtのobj.setfont()の説明 + exedit.auf文字列抽出で確定
    table = {
        "0": "標準文字",
        "1": "影付き文字",
        "2": "影付き文字(薄)",
        "3": "縁取り文字",
        "4": "縁取り文字(細)",
    }
    return table.get(value, value)


def conv_colorshift_type(value: str) -> str:
    table = {"0": "赤緑A"}  # 他のtype値は未検証
    return table.get(value, value)


def conv_blend(value: str) -> str:
    table = {"0": "通常"}  # 他のblend値は未検証。effect.confでキー名のみ確定(blend=合成モード)
    return table.get(value, value)


# ------------------------------------------------------------
# 3.5 数値↔名称の完全対応表
#     AviUtl2の effect.conf (公式の旧スクリプト互換定義) から転記。
#     「一覧の並び順=番号」という規則が、文字揃え・アニメーション効果・
#     カスタムオブジェクト・カメラ効果すべてで一致することを実機検証済み。
#     script.anm2 / script.obj2 / script.cam2 の@名前の並び順とも完全一致。
# ------------------------------------------------------------

ANIMATION_EFFECT_MAP = {
    "0": "震える", "1": "振り子", "2": "弾む",
    "3": "座標の拡大縮小(個別オブジェクト)", "4": "画面外から登場",
    "5": "ランダム方向から登場", "6": "拡大縮小して登場",
    "7": "ランダム間隔で落ちながら登場", "8": "弾んで登場",
    "9": "広がって登場", "10": "起き上がって登場",
    "11": "何処からともなく登場", "12": "反復移動",
    "13": "座標の回転(個別オブジェクト)", "14": "立方体(カメラ制御)",
    "15": "球体(カメラ制御)", "16": "砕け散る", "17": "点滅",
    "18": "点滅して登場", "19": "簡易変形", "20": "簡易変形(カメラ制御)",
    "21": "リール回転", "22": "万華鏡", "23": "円形配置", "24": "ランダム配置",
    # 25以降(ミラー、粒子化、メッシュ変形、揺らぎ)はAviUtl2の新規効果で、
    # 旧.exoには存在しないため変換対象外
}

CUSTOM_OBJECT_MAP = {
    "0": "集中線", "1": "走査線", "2": "カウンター", "3": "レンズフレア",
    "4": "雲", "5": "星", "6": "雪", "7": "雨",
    "8": "ランダム小物配置(カメラ制御)", "9": "ライン(移動軌跡)",
    "10": "扇型", "11": "多角形", "12": "周辺ボケ光量", "13": "フレア", "14": "水面",
}

CAMERA_EFFECT_MAP = {
    "0": "手ぶれ", "1": "目標中心回転", "2": "目標サイズ固定視野角",
}

TRACKMODE_MAP = {
    "1": "直線移動", "2": "補間移動", "3": "瞬間移動", "4": "直線移動",
    "5": "移動量指定", "6": "ランダム移動", "7": "補間移動", "8": "反復移動",
}


# 各フィルタのルール構造(リファクタリング版):
#   aup2_name  : 変換後のフィルタ名(effect.conf の [OldScript] 節でリネームされていれば反映)
#   renames    : {exoのキー: aup2のキー} キー名が変わるものだけ書く
#   value_conv : {exoのキー: 変換関数}   値も変換が要るものだけ書く(キーはexo側の名前)
#   text_field : (exoのキー, aup2のキー) UTF-16LE 16進デコードが要るテキスト専用
#   defaults   : aup2側だけに存在する新パラメータを埋めるデフォルト値
#
# renames/value_convに無いキーは「そのまま同名で引き継ぐ」(パススルー)。
# これにより、まだ検証していないキーも失われずに出力される。
FILTER_MAP = {
    "テキスト": {
        "aup2_name": "テキスト",
        "text_field": ("text", "テキスト"),
        "renames": {
            "font": "フォント",
            "color": "文字色",
            "color2": "影・縁色",
            "align": "文字揃え",
            "type": "文字装飾",
            "autoadjust": "オブジェクトの長さを自動調節",
            "移動座標上に表示する": "移動座標上に表示",
            "spacing_x": "字間",
            "spacing_y": "行間",
        },
        "value_conv": {
            "align": conv_align,
            "type": conv_text_type,
        },
        "defaults": {
            "字間": "0.00",
            "行間": "0.00",
        },
    },
    "標準描画": {
        "aup2_name": "標準描画",
        "renames": {
            "回転": "Z軸回転",  # effect.confで確定
            "blend": "合成モード",
        },
        "value_conv": {
            "blend": conv_blend,
        },
        "defaults": {
            "Group": "1", "中心X": "0.00", "中心Y": "0.00", "中心Z": "0.00",
            "Group3": "1", "X軸回転": "0.00", "Y軸回転": "0.00",
            "Group2": "1", "縦横比": "0.000",
        },
    },
    "色ずれ": {
        "aup2_name": "色ずれ",
        "renames": {
            "type": "色ずれの種類",
        },
        "value_conv": {
            "type": conv_colorshift_type,
        },
        "defaults": {},
    },
    # ---- ここから先は effect.conf のキー改名情報のみが根拠。
    #      renamesに無いキーはパススルーだが、実機未検証のため注意 ----
    "グラデーション": {
        "aup2_name": "グラデーション",
        "renames": {"color": "開始色", "color2": "終了色", "blend": "合成モード", "type": "形状"},
        "value_conv": {"blend": conv_blend},
        "defaults": {},
    },
    "ノイズ": {
        "aup2_name": "ノイズ",
        "renames": {"type": "ノイズの種類", "seed": "シード", "mode": "合成モード"},
        "defaults": {},
    },
    "単色化": {
        "aup2_name": "単色化",
        "renames": {"color": "色"},
        "defaults": {},
    },
    "マスク": {
        "aup2_name": "マスク",
        "renames": {"type": "マスクの種類"},
        "defaults": {},
    },
    "発光": {
        "aup2_name": "発光",
        "renames": {"color": "光色", "no_color": "光色"},
        "defaults": {},
    },
    "閃光": {
        "aup2_name": "閃光",
        "renames": {"color": "光色", "no_color": "光色", "mode": "合成モード"},
        "defaults": {},
    },
    "色調補正": {
        "aup2_name": "色調補正",
        "renames": {"ｺﾝﾄﾗｽﾄ": "コントラスト"},
        "defaults": {},
    },
    "縁取り": {
        "aup2_name": "縁取り",
        "renames": {"color": "縁色"},
        "defaults": {},
    },
    "リサイズ": {
        "aup2_name": "リサイズ",
        "renames": {"ドット数でサイズ指定": "ピクセル数でサイズ指定"},
        "defaults": {},
    },
    "ルミナンスキー": {
        "aup2_name": "ルミナンスキー",
        "renames": {"ぼかし": "輝度範囲", "type": "モード"},
        "defaults": {},
    },
    "カラーキー": {
        "aup2_name": "カラーキー",
        "renames": {"color_yc": "基準色"},
        "defaults": {},
    },
    "クロマキー": {
        "aup2_name": "クロマキー",
        "renames": {"color_yc": "基準色"},
        "defaults": {},
    },
    "特定色域変換": {
        "aup2_name": "特定色域変換",
        "renames": {"color_yc": "変換前の色", "color_yc2": "変換後の色"},
        "defaults": {},
    },
    "ドロップシャドウ": {
        "aup2_name": "ドロップシャドウ",
        "renames": {"color": "影色"},
        "defaults": {},
    },
    "エッジ抽出": {
        "aup2_name": "エッジ抽出",
        "renames": {"color": "色"},
        "defaults": {},
    },
    "ライト": {
        "aup2_name": "ライト",
        "renames": {"color": "色"},
        "defaults": {},
    },
    "ディスプレイスメントマップ": {
        "aup2_name": "ディスプレイスメントマップ",
        "renames": {"type": "変形方法", "name": "マップの種類", "param0": "変形X", "param1": "変形Y"},
        "defaults": {},
    },
    "グロー": {
        "aup2_name": "グロー",
        "renames": {"color": "光色", "no_color": "光色", "type": "形状"},
        "defaults": {},
    },
    "ワイプ": {
        "aup2_name": "ワイプ",
        "renames": {"type": "ワイプの種類", "name": "ワイプの種類"},
        "defaults": {},
    },
    "ミラー": {
        "aup2_name": "ミラー",
        "renames": {"type": "ミラーの方向"},
        "defaults": {},
    },
    "動画ファイル": {
        "aup2_name": "動画ファイル",
        "renames": {"file": "ファイル"},
        "defaults": {},
    },
    "画像ファイル": {
        "aup2_name": "画像ファイル",
        "renames": {"file": "ファイル"},
        "defaults": {},
    },
    "音声ファイル": {
        "aup2_name": "音声ファイル",
        "renames": {"file": "ファイル"},
        "defaults": {},
    },
    "図形": {
        "aup2_name": "図形",
        "renames": {"type": "図形の種類", "name": "図形の種類", "color": "色"},
        "defaults": {},
    },
    # フィルタ名自体がリネームされているもの(effect.confの[OldScript]節)
    "拡張描画": {
        "aup2_name": "標準描画",
        "renames": {"回転": "Z軸回転", "blend": "合成モード"},
        "value_conv": {"blend": conv_blend},
        "defaults": {},
    },
    "標準再生": {
        "aup2_name": "音声再生",
        "renames": {},
        "defaults": {},
    },
}


# ------------------------------------------------------------
# 4. 1オブジェクト分を aup2 の行リストに変換
# ------------------------------------------------------------

def convert_object(obj_id: str, obj_section: dict, sub_sections: dict) -> list[str]:
    out: list[str] = []

    start = int(obj_section.get("start", "1"))
    end = int(obj_section.get("end", "1"))
    layer = int(obj_section.get("layer", "1"))

    # exoは1始まり、aup2は0始まりという前提での変換(要検証の仮定)
    frame_start = start - 1
    frame_end = end - 1
    aup2_layer = layer - 1

    out.append(f"[{obj_id}]")
    out.append(f"layer={aup2_layer}")
    out.append(f"frame={frame_start},{frame_end}")

    sub_index = 0
    for key in sorted(sub_sections.keys(), key=lambda k: int(k.split(".")[1])):
        sub = sub_sections[key]
        exo_filter_name = sub.get("_name", "")

        if exo_filter_name not in FILTER_MAP:
            print(f"  [警告] 未対応フィルタ '{exo_filter_name}' ({key}) をスキップしました", file=sys.stderr)
            continue

        rule = FILTER_MAP[exo_filter_name]
        out.append(f"[{obj_id}.{sub_index}]")
        out.append(f"effect.name={rule['aup2_name']}")

        text_exo_key = None
        if "text_field" in rule:
            text_exo_key, text_aup2_key = rule["text_field"]
            if text_exo_key in sub:
                out.append(f"{text_aup2_key}={decode_exo_text(sub[text_exo_key])}")

        renames = rule.get("renames", {})
        value_conv = rule.get("value_conv", {})
        emitted_keys: set[str] = set()

        for exo_key, value in sub.items():
            if exo_key == "_name" or exo_key == text_exo_key:
                continue  # 処理済み、またはフィルタ名そのもの
            aup2_key = renames.get(exo_key, exo_key)  # リネーム無指定ならそのまま引き継ぐ
            if exo_key in value_conv:
                value = value_conv[exo_key](value)
            out.append(f"{aup2_key}={value}")
            emitted_keys.add(aup2_key)

        # デフォルト値は、リネーム経由で既に出力済みのキーには重ねて出さない
        for default_key, default_value in rule.get("defaults", {}).items():
            if default_key in emitted_keys:
                continue
            out.append(f"{default_key}={default_value}")

        sub_index += 1

    return out


# ------------------------------------------------------------
# 5. ファイル全体の変換
# ------------------------------------------------------------

def convert_exo_to_aup2(exo_path: Path, out_path: Path) -> None:
    data = parse_exo(exo_path)

    header = data.get("exedit", {})
    width = header.get("width", "1920")
    height = header.get("height", "1080")
    rate = header.get("rate", "30")
    audio_rate = header.get("audio_rate", "44100")

    lines: list[str] = []
    lines.append("[project]")
    lines.append("version=2011300")
    lines.append(f"file={out_path}")
    lines.append("display.scene=0")
    lines.append("preview.scene=0")
    lines.append("display.scene.list.label=")
    lines.append("[scene.0]")
    lines.append("scene=0")
    lines.append("name=Root")
    lines.append("label=")
    lines.append(f"video.width={width}")
    lines.append(f"video.height={height}")
    lines.append(f"video.rate={rate}")
    lines.append("video.scale=1")
    lines.append(f"audio.rate={audio_rate}")
    lines.append("cursor.frame=0")
    lines.append("cursor.layer=0")
    lines.append("preview.frame=0")
    lines.append("display.frame=0")
    lines.append("display.layer=0")
    lines.append("display.zoom=10000")
    lines.append("display.order=0")
    lines.append("display.camera=")
    lines.append("display.grid.x=16,-16")
    lines.append("display.grid.y=16,-16")
    lines.append("display.grid.width=200")
    lines.append("display.grid.height=200")
    lines.append("display.grid.step=200.000000")
    lines.append("display.grid.range=10000.000000")
    lines.append("display.tempo.bpm=120.000000")
    lines.append("display.tempo.beat=4")
    lines.append("display.tempo.start=0.000000")
    lines.append("display.tempo.offset=0.000000")

    obj_ids = sorted(
        {k for k in data.keys() if re.match(r"^\d+$", k)},
        key=int,
    )

    for obj_id in obj_ids:
        obj_section = data[obj_id]
        sub_sections = {
            k: v for k, v in data.items()
            if re.match(rf"^{re.escape(obj_id)}\.\d+$", k)
        }
        print(f"オブジェクト [{obj_id}] を変換中...")
        lines.extend(convert_object(obj_id, obj_section, sub_sections))

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n変換完了: {out_path}")


# ------------------------------------------------------------
# 6. 実行
# ------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python exo_to_aup2.py 入力.exo [出力.aup2]")
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else in_path.with_suffix(".aup2")

    convert_exo_to_aup2(in_path, out_path)