#!/usr/bin/env python3
"""
decode_shortcut.py

Decode Apple .shortcut files (CMS-wrapped binary plists) into:

A) XML plist output
B) Human-readable action list
C) Both

Usage:
    python decode_shortcut.py -A My.shortcut
    python decode_shortcut.py -B My.shortcut
    python decode_shortcut.py -C My1.shortcut My2.shortcut
"""

import argparse
import plistlib
import sys
from pathlib import Path

# Pure-Python ASN.1 library (builtin in this environment)
from asn1crypto import cms


def extract_cms_payload(shortcut_path: Path) -> bytes:
    """Extract the inner plist payload from a CMS-wrapped .shortcut file."""
    data = shortcut_path.read_bytes()
    content_info = cms.ContentInfo.load(data)

    if content_info['content_type'].native != 'signed_data':
        raise ValueError("File is not CMS signedData")

    signed_data = content_info['content']

    # Per CMS spec, content is inside encap_content_info
    encap = signed_data['encap_content_info']

    if encap['content'] is None:
        raise ValueError("Shortcut contains no embedded plist content")

    return encap['content'].native


def decode_plist_to_dict(plist_bytes: bytes) -> dict:
    """Decode binary plist to a Python dictionary."""
    try:
        return plistlib.loads(plist_bytes)
    except Exception as e:
        raise ValueError(f"Failed to decode plist: {e}")


def write_xml_plist(plist_dict: dict, output_path: Path):
    """Write plist dict as XML."""
    xml_data = plistlib.dumps(plist_dict, fmt=plistlib.FMT_XML)
    output_path.write_bytes(xml_data)


def render_action_list(plist_dict: dict) -> str:
    """Produce a clean, readable human-oriented description of workflow actions."""
    wf = plist_dict.get("WFWorkflow") or plist_dict  # Some versions have nested WFWorkflow key

    actions = wf.get("WFWorkflowActions", [])
    output_lines = []

    for i, action in enumerate(actions, start=1):
        action_type = action.get("WFWorkflowActionIdentifier", "UnknownAction")
        params = action.get("WFWorkflowActionParameters", {})

        output_lines.append(f"\n=== Action {i}: {action_type} ===")

        if params:
            for k, v in params.items():
                output_lines.append(f"{k}: {v}")
        else:
            output_lines.append("(No parameters)")

    return "\n".join(output_lines)


def process_shortcut(path: Path, do_xml: bool, do_actions: bool):
    print(f"\nProcessing: {path}")

    try:
        payload = extract_cms_payload(path)
    except Exception as e:
        print(f"ERROR: Failed to extract CMS content: {e}")
        return

    try:
        plist_dict = decode_plist_to_dict(payload)
    except Exception as e:
        print(f"ERROR: Plist decode failed: {e}")
        return

    base = path.stem

    # Option A: Write XML plist
    if do_xml:
        xml_path = path.with_suffix(".xml")
        write_xml_plist(plist_dict, xml_path)
        print(f"→ XML plist written to {xml_path}")

    # Option B: Write human-readable action list
    if do_actions:
        txt_path = path.with_suffix(".actions.txt")
        readable = render_action_list(plist_dict)
        txt_path.write_text(readable, encoding="utf-8")
        print(f"→ Action list written to {txt_path}")


def main():
    parser = argparse.ArgumentParser(description="Decode .shortcut files")
    parser.add_argument(
        "files",
        nargs="+",
        help="Shortcut files to decode",
    )
    parser.add_argument(
        "-A",
        "--xml",
        action="store_true",
        help="Produce XML plist output",
    )
    parser.add_argument(
        "-B",
        "--actions",
        action="store_true",
        help="Produce human-readable action list",
    )
    parser.add_argument(
        "-C",
        "--both",
        action="store_true",
        help="Produce BOTH XML and action list",
    )
    args = parser.parse_args()

    if not (args.xml or args.actions or args.both):
        print("ERROR: You must specify -A, -B, or -C.")
        sys.exit(1)

    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"ERROR: File not found: {path}")
            continue

        process_shortcut(
            path,
            do_xml=(args.xml or args.both),
            do_actions=(args.actions or args.both),
        )


if __name__ == "__main__":
    main()
