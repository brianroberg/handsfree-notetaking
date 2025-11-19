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

# Pure-Python ASN.1 library (installed via pip)
from asn1crypto import cms

try:
    import lzfse
except ModuleNotFoundError:  # pragma: no cover - dependency hint for users
    lzfse = None


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


def extract_aea1_lzfse_payload(shortcut_path: Path) -> bytes:
    """
    Extract the inner plist payload from Apple's newer AEA1 container that
    wraps an LZFSE-compressed plist.
    """
    if lzfse is None:
        raise ValueError("Missing dependency: install lzfse to parse AEA1 shortcuts")

    data = shortcut_path.read_bytes()

    if not data.startswith(b"AEA1"):
        raise ValueError("Not an AEA1/LZFSE shortcut")

    # First 4 bytes: magic "AEA1"
    # Next 4 bytes: unused/reserved (currently zeros)
    # Next 4 bytes: little-endian length of the signing certificate plist
    cert_len = int.from_bytes(data[8:12], "little")

    # The certificate chain plist is rarely useful for decoding, but we skip
    # past it to reach the payload section.
    payload_start = 12 + cert_len

    # The actual workflow payload is stored in an LZFSE-compressed block
    # flagged by the "bvx" magic. Grab from that magic onward.
    magic_index = data.find(b"bvx", payload_start)
    if magic_index == -1:
        raise ValueError("LZFSE section not found inside AEA1 container")

    compressed = data[magic_index:]
    decompressed = lzfse.decompress(compressed)

    plist_index = decompressed.find(b"bplist00")
    if plist_index == -1:
        raise ValueError("Embedded plist not found after decompressing AEA1 payload")

    return decompressed[plist_index:]


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
        try:
            payload = extract_aea1_lzfse_payload(path)
        except Exception as e2:
            print(f"ERROR: Failed to extract shortcut payload.\n- CMS parse error: {e}\n- AEA1 parse error: {e2}")
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
