"""Remove only locally learned glyph dictionary files (not OCR resources)."""
from kain_maple_translator.glyph_dictionary import GlyphDictionary
if __name__=='__main__':
    db=GlyphDictionary()
    print('Clearing glyph dictionary folder:',db.folder)
    db.clear_all()
    print('Glyph dictionaries cleared. Restart the translator.')
