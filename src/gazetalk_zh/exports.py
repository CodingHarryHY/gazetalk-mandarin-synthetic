from __future__ import annotations

import csv
import html
import io
import json
import re
from pathlib import Path
from typing import Any

from .generate import checked_records, load_run
from .provenance import digest, now, run_lock, write_json, write_jsonl, write_text
from .validation import quality_flags


def csv_text(rows: list[dict[str, Any]], fields: list[str]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        safe = {}
        for field in fields:
            value = row.get(field, "")
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            safe[field] = value
        writer.writerow(safe)
    return "\ufeff" + stream.getvalue()


def chat_segments(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", text)
    result = []
    replacements = str.maketrans({"[": "（", "]": "）", "<": "＜", ">": "＞", "@": "＠", "*": "＊", "#": "＃"})
    for part in parts:
        if not part.strip():
            continue
        terminator = "?" if part.rstrip().endswith(("?", "？")) else "!" if part.rstrip().endswith(("!", "！")) else "."
        body = part.strip().rstrip("。！？!?.").translate(replacements)
        body = re.sub(r"…+|\.{3,}", "，", body)
        body = " ".join(body.split()).strip()
        if body:
            result.append(body + " " + terminator)
    if not result:
        raise ValueError("Cannot export an empty CHAT utterance.")
    return result


def check_chat(text: str) -> int:
    lines = text.splitlines()
    if lines[:3] != ["@UTF8", "@Begin", "@Languages:\tzho"] or lines[-1:] != ["@End"]:
        raise ValueError("Invalid generated CHAT headers or ending.")
    if sum(line.startswith("@Participants:") for line in lines) != 1 or sum(line.startswith("@ID:") for line in lines) != 2:
        raise ValueError("Invalid generated CHAT participant metadata.")
    main = [line for line in lines if line.startswith("*")]
    if not main or any(not re.fullmatch(r"\*(INV|PAR):\t.+ [.!?]", line) for line in main):
        raise ValueError("Invalid generated CHAT main tier.")
    return len(main)


def render_chat(row: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    lines = ["@UTF8", "@Begin", "@Languages:\tzho",
             "@Participants:\tPAR Synthetic_Patient Participant, INV Synthetic_Therapist Investigator",
             "@ID:\tzho|SyntheticDialogue|PAR|||" + row["profile"] + "||Participant|||",
             "@ID:\tzho|SyntheticDialogue|INV|||||Investigator|||",
             "@Comment:\tFully synthetic orthographic export; no audio or measured timing.",
             "@Comment:\tNo clinical error annotations or automatic morphological analysis.",
             "@Comment:\tDialogue_ID: " + row["dialogue_id"],
             "@Comment:\tPersona_ID: " + row["persona_id"],
             "@Comment:\tProfile: " + row["profile"],
             "@Comment:\tSession_topic: " + row["session_topic"]]
    mapping = []
    main_index = 0
    for index, turn in enumerate(json.loads(row["text"])["dialogue"], 1):
        segments = chat_segments(turn["utterance"])
        first = main_index + 1
        speaker = "INV" if turn["speaker"] == "therapist" else "PAR"
        for segment in segments:
            lines.append(f"*{speaker}:\t{segment}")
            main_index += 1
        mapping.append({"dialogue_id": row["dialogue_id"], "turn_index": index,
                        "main_tier_indices": list(range(first, main_index + 1)), "speaker": turn["speaker"],
                        "source_utterance": turn["utterance"], "exported_segments": segments,
                        "transformation": "Sentence segmentation, reserved-character escaping, orthographic punctuation normalization."})
    lines.append("@End")
    text = "\n".join(lines) + "\n"
    check_chat(text)
    return text, mapping


def export(run: Path) -> dict[str, Any]:
    with run_lock(run):
        _, snapshot, personas, jobs = load_run(run)
        rows = checked_records(run, snapshot, jobs)
        if not rows:
            raise ValueError("No validated dialogues to export; no model output is fabricated.")
        output_hash = digest(rows)
        target = run / "exports" / output_hash[:16]
        if (target / "manifest.json").exists():
            return {"status": "already_exported", "directory": str(target), "records": len(rows)}
        if target.exists():
            raise ValueError("Incomplete export directory exists; preserve it and remove it from the export path before retrying.")
        by_persona = {p["persona_id"]: p for p in personas}
        by_job = {j["dialogue_id"]: j for j in jobs}
        reviews, turn_rows, maps, cards = [], [], [], []
        for row in rows:
            identifier = row["dialogue_id"]
            dialogue = json.loads(row["text"])["dialogue"]
            chat, mapping = render_chat(row)
            write_text(target / "chat" / (identifier + ".cha"), chat)
            maps.extend(mapping)
            review = {"dialogue_id": identifier, "persona_id": row["persona_id"], "profile": row["profile"],
                      "severity": by_persona[row["persona_id"]]["severity"], "topic": row["session_topic"],
                      "mode": by_job[identifier]["conversation_mode"], "assigned_primary_strategy": row["therapist_strategy"],
                      "turn_count": len(dialogue), "automatic_flags": "; ".join(quality_flags(dialogue)),
                      "review_status": "not_reviewed", "reviewer": "", "reviewed_at": "",
                      "completion_rating": "", "coherence_rating": "", "support_rating": "",
                      "profile_plausibility_rating": "", "stereotype_concern": "", "notes": "",
                      "dialogue_text": "\n".join(f"{i}. {t['speaker']}: {t['utterance']}" for i, t in enumerate(dialogue, 1))}
            reviews.append(review)
            for index, turn in enumerate(dialogue, 1):
                turn_rows.append({"dialogue_id": identifier, "turn_index": index, **turn,
                                  "review_status": "not_reviewed", "issue": "", "notes": ""})
            utterances = "".join("<p><b>" + html.escape(t["speaker"]) + ":</b> " + html.escape(t["utterance"]) + "</p>" for t in dialogue)
            cards.append("<details><summary>" + html.escape(f"{identifier} | {row['profile']} | {len(dialogue)} turns") + "</summary>" + utterances + "</details>")
        write_jsonl(target / "chat" / "turn_map.jsonl", maps)
        write_text(target / "review" / "dialogues.csv", csv_text(reviews, list(reviews[0])))
        write_text(target / "review" / "turns.csv", csv_text(turn_rows, list(turn_rows[0])))
        write_text(target / "review" / "index.html", '<!doctype html><html lang="en"><meta charset="utf-8"><title>Mandarin dialogue review</title>'
                   '<style>body{max-width:900px;margin:32px auto;font:17px system-ui;line-height:1.7;padding:0 20px}details{border:1px solid #ccc;padding:14px;margin:12px 0}summary{cursor:pointer}</style>'
                   '<h1>Mandarin dialogue review</h1><p>Fully synthetic. Human review is not completed. Edit the CSV files to record ratings; this page does not save ratings.</p>'
                   + "".join(cards) + '</html>')
        result = {"status": "exported", "created_at": now(), "directory": str(target), "records": len(rows),
                  "output_hash": output_hash, "internal_chat_checks": "pass", "external_chat_validation": "not_run",
                  "note": "The internal checker is not CLAN or Chatter. CHAT tokens are not Mandarin word segmentation."}
        write_json(target / "manifest.json", result)
        return result
