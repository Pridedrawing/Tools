#!/usr/bin/env python

from config import api_key, glossaries as gloss_dict
import deepl
import json

debug = 0

src_lang = {"en", "de"}
tgt_lang = {"en", "de", "it", "es", "nl", "pl", "fr", "pt"}

entries = {
    "[name]": "[name]",
    "{b}": "{b}",
    "{/b}": "{/b}",
    "{/i}": "{/i}",
    "{i}": "{i}",
    "[RelVal]": "[RelVal]",
}

tl = deepl.Translator(api_key)


if debug != 0:
    print("Deleting previous glossaries...")
    for glossary in tl.list_glossaries():
        translator.delete_glossary(glossary)

for src in src_lang:
    gloss_dict[src] = {}
    for tgt in tgt_lang:
        if src == tgt:
            continue
        gloss_dict[src][tgt] = tl.create_glossary(
            src + "_" + tgt,
            source_lang=src,
            target_lang=tgt,
            entries=entries,
        ).glossary_id
        print(gloss_dict[src][tgt])

with open("glossaries.json", 'w', encoding="utf-8") as file:
    str = json.dumps(gloss_dict, indent=4)
    print(str)
    file.seek(0)
    file.truncate()
    file.write(str)
