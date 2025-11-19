This system uses Apple Shortcuts to record notes entirely through voice prompts. The principal use case I have in mind is when I'm listening to audiobooks while driving. The flow goes like this:
1. While listening to an audiobook in [ShelfPlayer](https://github.com/rasmuslos/ShelfPlayer), I decide I want to record a note and invoke the "Take a Note" shortcut with "Siri, take a note."
2. This shortcut first pauses the audiobook and then calls a second shortcut called, "Capture Dictated Note Input."
3. This shortcut solicits my note via a text prompt.
4. Then it reads back what it heard for confirmation and asks whether to save it.
	1. If yes, it returns the text to the first shortcut.
	2. If not, it tries again by *calling itself*.
5. Back in the "Take a Note" shortcut, checks whether a note with the current date exists in a "Dictated Notes" folder in the Apple Notes app.
	1. If so, it appends the dictated text to the existing note.
	2. If not, it creates a new note containing the dictated text.
6. Then the script asks if I want to record another note.
	1. If yes, it calls itself to start over again with a new note.
	2. If no, it resumes playback in ShelfPlayer.
# Decoding Apple `.shortcut` Files

Apple Shortcuts files (`.shortcut`) are not simple JSON or XML documents.  
During development of this tool, we found that iOS and macOS use **multiple different internal formats**, and most documentation online only describes the older ZIP-based format.

This section summarizes everything learned while reverse-engineering modern `.shortcut` files and explains what this tool does to decode them.

---

## 📌 What We Learned About `.shortcut` File Formats

### ### 1. **Not ZIP archives (anymore)**
Older versions of Shortcuts exported `.shortcut` files as ZIP archives containing two inner files:

- `ShortcutWorkflow.plist`
- `ShortcutInfo.plist`

These could be unzipped with:

```
unzip MyShortcut.shortcut
```

However, newer iOS/macOS versions (iOS 17+, macOS Sonoma and later) **no longer use ZIP**.  
When attempting to unzip a modern shortcut, we observed:

```
Archive:  Take a Note.shortcut
  End-of-central-directory signature not found.
unzip:  cannot find zipfile directory...
```

This indicates the file is **not a ZIP container**.

---

### 2. **Not a top-level plist**
We next attempted:

```
plutil -p Take\ a\ Note.shortcut
```

The result:

```
Property List error: Unexpected character A at line 1
```

This shows the file:

- Is not plain XML
- Is not plain binary plist
- Does not start with a plist header

So the file has some other kind of wrapper.

---

### 3. **Contains binary data starting with `AEA1` and `bplist00`**
Running `strings` on the file:

```
strings Take\ a\ Note.shortcut | head
```

revealed:

```
AEA1
bplist00
SigningCertificateChain
Apple System Integration CA
Apple Certification Authority
```

This output was the breakthrough:

- `AEA1` indicates **CMS (Cryptographic Message Syntax)**  
- `bplist00` means a binary plist is embedded *inside* the CMS envelope  
- `SigningCertificateChain` shows that the shortcut is **digitally signed** with Apple certificates  
- ASN.1 sequences (`0x30 0x82 …`) confirm CMS/PKCS#7 structure  

So the shortcut file is a:

> **CMS-signed binary plist encoding of the workflow**,  
> **not a zip**,  
> **not a raw plist**.

This is why `plutil` and `unzip` both fail.

---

### 4. **The actual workflow is embedded as the CMS payload**
Inside the CMS wrapper lives the real data — a binary plist containing keys like:

- `WFWorkflow`
- `WFWorkflowClientVersion`
- `WFWorkflowActions`
- etc.

To access that plist, the CMS envelope must be decoded first.

---

## 📌 Why a Custom Script Is Needed

Apple provides the `security cms` command-line tool on macOS, which can decode CMS data:

```
security cms -D -i My.shortcut -o decoded.plist
```

But:

- This does **not** exist on Linux or Windows  
- It cannot be used on iOS/iPadOS  
- It sometimes fails on nested archives  
- Developers often want version-control or CI support outside macOS

To support decoding on any platform, a pure-Python solution is needed.

---

## 🧰 What This Script Does

The included script `decode_shortcut.py` uses **pure Python** (via `asn1crypto`) to:

1. Parse the CMS wrapper  
2. Extract the signed binary plist payload  
3. Decode the plist into a Python dictionary  
4. Optionally convert it to XML (Option A)  
5. Optionally generate a clean, human-readable action list (Option B)  
6. Optionally produce both outputs (Option C)

This makes it possible to:

- Perform version control on shortcuts  
- Inspect workflow logic outside Apple platforms  
- Document behavior in readable or diffable form  
- Understand internal structure for debugging or auditing  
- Work with Shortcuts in cross-platform environments

---

## 🎛️ Command Line Usage

```bash
python decode_shortcut.py -A My.shortcut        # Output XML plist
python decode_shortcut.py -B My.shortcut        # Output action list
python decode_shortcut.py -C *.shortcut         # Do both for multiple files
```

The script produces:

- `My.xml` — fully decoded XML plist  
- `My.actions.txt` — readable list of workflow actions  

---

## 📋 Output Examples

### XML Mode
Produces a complete plist representation suitable for Git diffs.

### Action List Mode
Produces a human-oriented listing:

```
=== Action 1: WFAskForInput ===
WFInputPrompt: What would you like to add?
WFInputType: Text

=== Action 2: WFSpeakText ===
WFText: You said: ...
```

This makes it easy to understand what a shortcut does without loading it into the Shortcuts app.

---

If you enhance the script or add new export formats (such as Markdown or JSON), feel free to extend this documentation.
