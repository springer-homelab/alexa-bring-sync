"""Intelligent NLU Parsing Engine for German Grocery Items."""
from __future__ import annotations

import re
import json
import os
import time
import asyncio
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

OTA_VOCAB_URL = "https://raw.githubusercontent.com/springer-homelab/alexa-bring-sync/main/bring_vocab.json"
CACHE_EXPIRY_SECONDS = 86400  # 24 hours

class NLUParsingEngine:
    def __init__(self, vocab: dict[str, Any] | None = None) -> None:
        if vocab is None:
            vocab = {}
            
        self.grocery_adjectives = set(vocab.get('grocery_adjectives', [
            'wiener', 'saure', 'saurer', 'saures', 'sauren', 'rote', 'roter', 'rotes', 'roten', 'grüne', 'grüner', 'grünes', 'grünen',
            'frische', 'frischer', 'frisches', 'frischen', 'passierte', 'passierter', 'passiertes', 'passierten',
            'gehackte', 'gehackter', 'gehacktes', 'gehackten', 'getrocknete', 'getrockneter', 'getrocknetes', 'getrockneten',
            'geriebene', 'geriebener', 'geriebenes', 'geriebenen', 'braune', 'brauner', 'braunes', 'braunen',
            'italienische', 'italienischer', 'italienisches', 'italienischen', 'griechische', 'griechischer', 'griechisches', 'griechischen',
            'gemischte', 'gemischter', 'gemischtes', 'gemischten', 'stille', 'stiller', 'stilles', 'stillen',
            'scharfe', 'scharfer', 'scharfes', 'scharfen', 'süße', 'süßer', 'süßes', 'süßen', 'milde', 'milder', 'mildes', 'milden',
            'feine', 'feiner', 'feines', 'feinen', 'grobe', 'grober', 'grobes', 'groben', 'schwarze', 'schwarzer', 'schwarzes', 'schwarzen',
            'weiße', 'weißer', 'weißes', 'weißen', 'helle', 'heller', 'helles', 'hellen', 'dunkle', 'dunkler', 'dunkles', 'dunklen',
            'gefrorene', 'gefrorener', 'gefrorenes', 'gefrorenen', 'tiefgekühlte', 'tiefgekühlter', 'tiefgekühltes', 'tiefgekühlten',
            'bio', 'freiland', 'vegan', 'vegane', 'veganer', 'veganes', 'veganen',
            'vegetarisch', 'vegetarische', 'vegetarischer', 'vegetarisches', 'vegetarischen',
            'pflanzlich', 'pflanzliche', 'pflanzlicher', 'pflanzliches', 'pflanzlichen',
            'laktosefrei', 'laktosefreie', 'laktosefreies', 'laktosefreien', 'glutenfrei', 'glutenfreie', 'glutenfreies', 'glutenfreien',
            'alkoholfrei', 'alkoholfreie', 'alkoholfreier', 'alkoholfreies', 'alkoholfreien',
            'koffeinfrei', 'koffeinfreie', 'koffeinfreier', 'koffeinfreies', 'koffeinfreien',
            'zuckerfrei', 'zuckerfreie', 'zuckerfreier', 'zuckerfreies', 'zuckerfreien',
            'fettarm', 'fettarme', 'fettarmer', 'fettarmes', 'fettarmen',
            'nativ', 'native', 'nativer', 'natives', 'nativen',
            'kaltgepresst', 'kaltgepresste', 'kaltgepresster', 'kaltgepresstes', 'kaltgepressten',
            'regional', 'regionale', 'regionales', 'regionalen', 'asiatische', 'asiatischer', 'asiatischen'
        ]))
        
        self.compound_prefixes = set(vocab.get('compound_prefixes', [
            'oliven', 'sonnenblumen', 'raps', 'kokos', 'mandel', 'soja', 'hafer', 'dinkel',
            'puder', 'vanille', 'back', 'kakao', 'kakaopulver', 'vollmilch', 'zartbitter', 'schoko',
            'mineral', 'erdnuss', 'haselnuss', 'walnuss', 'cashew', 'kräuter', 'knoblauch', 'chili',
            'balsamico', 'weizen', 'roggen', 'mais', 'tiefkühl', 'tk',
            'puten', 'rinder', 'schweine', 'truthahn', 'kalbs', 'lamm', 'geflügel', 'hähnchen', 'hühner', 'fisch', 'lachs', 'thunfisch', 'garnelen',
            'kirsch', 'strauch', 'rispen', 'stauden', 'suppen', 'gewürz', 'koch', 'brat',
            'schafs', 'ziegen', 'hütten', 'mager', 'frisch', 'trocken', 'hart', 'weich', 'voll',
            'apfel', 'orangen', 'trauben', 'multi', 'multivitamin', 'zitronen', 'erdbeer',
            'himbeer', 'blaubeer', 'heidelbeer', 'pfefferminz', 'kamillen', 'fenchel',
            'toiletten', 'klo', 'küchen', 'alu', 'frischhalte', 'gefrier',
            'spül', 'spülmaschinen', 'wasch', 'putz', 'müll'
        ]))
        
        self.dependent_suffixes = set(vocab.get('dependent_suffixes', [
            'aufschnitt', 'geschnetzeltes', 'hackfleisch', 'filet', 'schnitzel', 'kotelett',
            'flocken', 'tabs', 'stäbchen', 'beutel', 'papier', 'paste', 'pulver', 'folie', 'rollen'
        ]))
        
        self.valid_base_compounds = set(vocab.get('valid_base_compounds', [
            'wurstaufschnitt', 'käseaufschnitt', 'salatgurke', 'salatgurken', 'kirschtomaten',
            'kochschinken', 'bratwurst', 'currywurst', 'leberwurst', 'teewurst', 'fleischwurst',
            'bockwurst', 'mettwurst', 'feta käse', 'fetakäse', 'frischkäse', 'frisch käse',
            'schmelzkäse', 'bergkäse', 'hartkäse', 'weichkäse', 'hafermilch', 'mandelmilch',
            'sojamilch', 'kokosmilch', 'vollmilch', 'heumilch', 'schlagsahne', 'sauresahne',
            'kaffeesahne', 'kräuterquark', 'speisequark', 'naturjoghurt', 'fruchtjoghurt',
            'nudelsalat', 'kartoffelsalat', 'eiersalat', 'thunfischsalat', 'gurkensalat',
            'tomatenmark', 'currypaste', 'backpulver', 'vanillezucker', 'puderzucker',
            'vollkornbrot', 'weißbrot', 'toastbrot', 'roggenbrot', 'aufbackbrötchen',
            'staudensellerie', 'pfefferminztee', 'kamillentee', 'fencheltee', 'alufolie',
            'frischhaltefolie', 'küchenrollen', 'backpapier', 'müllbeutel', 'toilettenpapier'
        ]))
        
        self.foreign_terms = set(vocab.get('foreign_terms', [
            'gustavo gusto', 'dr oetker', 'dr. oetker', 'ben and jerrys', 'ben & jerrys', 'haagen dazs',
            'ritter sport', 'ferrero rocher', 'mon cheri', 'mon chéri', 'kinder bueno', 'kinder riegel',
            'kinder country', 'kinder pingui', 'kinder maxi king', 'kinder joy', 'milch schnitte', 'coca cola',
            'coca-cola', 'coke zero', 'pepsi max', 'red bull', 'monster energy', 'paulaner spezi', 'san pellegrino',
            'funny frisch', 'funny-frisch', 'mini babybel', 'fritz kola', 'fritz-kola', 'fritz limo',
            'club mate', 'mio mio', 'mio mio mate', 'fuze tea', 'yogi tea', 'hohes c', 'true fruits',
            'oro di parma', 'coppenrath & wiese', 'coppenrath und wiese', 'head & shoulders', 'head and shoulders',
            'blend-a-med', 'blend a med', 'oral-b', 'oral b',
            'pollo fino', 'creme fraiche', 'crème fraîche', 'sour cream', 'cream cheese',
            'peanut butter', 'curry paste', 'pulled pork', 'ice tea', 'hot dog', 'french dressing',
            'sweet chili', 'sweet sour', 'barbecue sauce', 'bbq sauce', 'maple syrup',
            'tortilla chips', 'nacho chips', 'taco shells', 'salsa verde', 'salsa dip',
            'teriyaki sauce', 'sriracha sauce', 'sweet chili sauce', 'garam masala', 'tikka masala',
            'sushi reis', 'basmati reis', 'jasmin reis', 'mie nudeln', 'udon nudeln', 'ramen nudeln',
            'pesto genovese', 'pesto rosso', 'parmigiano reggiano', 'grana padano', 'pecorino romano',
            'prosciutto di parma', 'serrano schinken', 'iberico schinken', 'chicken nuggets', 'chicken wings',
            'ginger ale', 'tonic water', 'cold brew', 'chai latte', 'balsamico essig'
        ]))
        
        self.standalone_products = vocab.get('standalone_products', {
            'coca cola zero': 'Coca-Cola Zero',
            'coca-cola zero': 'Coca-Cola Zero',
            'coke zero': 'Coke Zero',
            'pepsi max': 'Pepsi Max',
            'paulaner spezi': 'Paulaner Spezi',
            'red bull': 'Red Bull',
            'monster energy': 'Monster Energy',
            'fritz kola': 'Fritz-Kola',
            'fritz-kola': 'Fritz-Kola',
            'club mate': 'Club-Mate',
            'mio mio mate': 'Mio Mio Mate',
            'kinder bueno': 'Kinder Bueno',
            'kinder riegel': 'Kinder Riegel',
            'kinder country': 'Kinder Country',
            'kinder pingui': 'Kinder Pingui',
            'kinder maxi king': 'Kinder Maxi King',
            'kinder joy': 'Kinder Joy',
            'kinder schokolade': 'Kinder Schokolade',
            'ferrero rocher': 'Ferrero Rocher',
            'mon cheri': 'Mon Chéri',
            'mon chéri': 'Mon Chéri',
            'ritter sport': 'Ritter Sport',
            'funny frisch': 'Funny-Frisch',
            'funny-frisch': 'Funny-Frisch',
            'mini babybel': 'Mini Babybel'
        })
        
        self.brand_map = vocab.get('brand_map', {
            'coca cola': 'Coca-Cola', 'coca-cola': 'Coca-Cola', 'coke zero': 'Coke Zero', 'coca cola zero': 'Coca-Cola Zero',
            'pepsi max': 'Pepsi Max', 'pepsi': 'Pepsi', 'fanta': 'Fanta', 'sprite': 'Sprite',
            'mezzo mix': 'Mezzo Mix', 'schwip schwap': 'Schwip Schwap', 'paulaner spezi': 'Paulaner Spezi', 'spezi': 'Spezi',
            'bionade': 'Bionade', 'fritz kola': 'Fritz-Kola', 'fritz-kola': 'Fritz-Kola', 'fritz limo': 'Fritz Limo',
            'club mate': 'Club-Mate', 'mio mio': 'Mio Mio', 'mio mio mate': 'Mio Mio Mate',
            'red bull': 'Red Bull', 'monster energy': 'Monster Energy', 'monster': 'Monster', 'rockstar': 'Rockstar', 'effect': 'Effect',
            'fuze tea': 'Fuze Tea', 'lipton': 'Lipton', 'arizona': 'AriZona',
            'gerolsteiner': 'Gerolsteiner', 'volvic': 'Volvic', 'vittel': 'Vittel', 'evian': 'Evian',
            'san pellegrino': 'San Pellegrino', 'adelholzener': 'Adelholzener', 'rhönsprudel': 'RhönSprudel',
            'apollinaris': 'Apollinaris', 'black forest': 'Black Forest',
            'hohes c': 'Hohes C', 'granini': 'Granini', 'valensina': 'Valensina', 'pfanner': 'Pfanner',
            'amecke': 'Amecke', 'innocent': 'Innocent', 'true fruits': 'True Fruits', 'rauch': 'Rauch',
            'krombacher': 'Krombacher', 'bitburger': 'Bitburger', 'warsteiner': 'Warsteiner',
            'becks': "Beck's", "beck's": "Beck's", 'paulaner': 'Paulaner', 'erdinger': 'Erdinger',
            'franziskaner': 'Franziskaner', 'augustiner': 'Augustiner', 'tegernseer': 'Tegernseer',
            'rothaus': 'Rothaus', 'heineken': 'Heineken', 'corona': 'Corona', 'desperados': 'Desperados',
            'astra': 'Astra', 'jever': 'Jever', 'veltins': 'Veltins', 'hasseröder': 'Hasseröder',
            'oettinger': 'Oettinger', 'schöfferhofer': 'Schöfferhofer', 'guinness': 'Guinness', 'flensburger': 'Flensburger',
            'tchibo': 'Tchibo', 'jacobs': 'Jacobs', 'dallmayr': 'Dallmayr', 'lavazza': 'Lavazza',
            'segafredo': 'Segafredo', 'melitta': 'Melitta', 'nespresso': 'Nespresso', 'senseo': 'Senseo',
            'dolce gusto': 'Dolce Gusto', 'teekanne': 'Teekanne', 'messmer': 'Meßmer', 'meßmer': 'Meßmer',
            'yogi tea': 'Yogi Tea', 'kaba': 'Kaba', 'nesquik': 'Nesquik', 'ovomaltine': 'Ovomaltine',
            'oatly': 'Oatly', 'alpro': 'Alpro', 'bärenmarke': 'Bärenmarke', 'weihenstephan': 'Weihenstephan',
            'landliebe': 'Landliebe', 'müllermilch': 'Müllermilch',
            'gustavo gusto': 'Gustavo Gusto', 'gusto gustavo': 'Gustavo Gusto',
            'dr oetker': 'Dr. Oetker', 'dr. oetker': 'Dr. Oetker', 'doktor oetker': 'Dr. Oetker',
            'wagner': 'Wagner', 'original wagner': 'Original Wagner',
            'frosta': 'Frosta', 'iglo': 'Iglo', 'mccain': 'McCain', 'coppenrath & wiese': 'Coppenrath & Wiese',
            'coppenrath und wiese': 'Coppenrath & Wiese',
            'ben and jerrys': "Ben & Jerry's", 'ben und jerrys': "Ben & Jerry's", 'ben & jerrys': "Ben & Jerry's",
            'haagen dazs': 'Häagen-Dazs', 'häagen dazs': 'Häagen-Dazs',
            'magnum': 'Magnum', 'cornetto': 'Cornetto', 'langnese': 'Langnese',
            'ritter sport': 'Ritter Sport', 'milka': 'Milka', 'lindt': 'Lindt',
            'ferrero rocher': 'Ferrero Rocher', 'mon cheri': 'Mon Chéri', 'mon chéri': 'Mon Chéri',
            'kinder bueno': 'Kinder Bueno', 'kinder riegel': 'Kinder Riegel', 'kinder country': 'Kinder Country',
            'kinder pingui': 'Kinder Pingui', 'kinder maxi king': 'Kinder Maxi King', 'kinder schokolade': 'Kinder Schokolade',
            'kinder joy': 'Kinder Joy', 'raffaello': 'Raffaello', 'giotto': 'Giotto', 'giottos': 'Giotto',
            'nutella': 'Nutella', 'duplo': 'Duplo', 'hanuta': 'Hanuta', 'toffifee': 'Toffifee', 'knoppers': 'Knoppers',
            'haribo': 'Haribo', 'katjes': 'Katjes', 'trolli': 'Trolli', 'nimm 2': 'Nimm 2',
            'chio': 'Chio', 'funny frisch': 'Funny-Frisch', 'funny-frisch': 'Funny-Frisch', 'pringles': 'Pringles',
            'lorenz': 'Lorenz', 'ültje': 'Ültje', 'ueltje': 'Ültje',
            'leibniz': 'Leibniz', 'bahlsen': 'Bahlsen', 'prinzenrolle': 'Prinzenrolle', 'prinzen rolle': 'Prinzenrolle',
            'oreo': 'Oreo', 'kitkat': 'KitKat', 'kit kat': 'KitKat', 'twix': 'Twix', 'snickers': 'Snickers',
            'mars': 'Mars', 'bounty': 'Bounty', 'milky way': 'Milky Way', 'm&ms': 'M&Ms', 'm&m': 'M&Ms',
            'milch schnitte': 'Milchschnitte', 'milchschnitte': 'Milchschnitte',
            'philadelphia': 'Philadelphia', 'almette': 'Almette', 'miree': 'Miree', 'bresso': 'Bresso',
            'exquisa': 'Exquisa', 'brunch': 'Brunch', 'kerrygold': 'Kerrygold', 'rama': 'Rama',
            'becel': 'Becel', 'meggle': 'Meggle', 'lätta': 'Lätta', 'laetta': 'Lätta',
            'leerdammer': 'Leerdammer', 'babybel': 'Babybel', 'mini babybel': 'Mini Babybel',
            'kiri': 'Kiri', 'zott': 'Zott', 'zottarella': 'Zottarella', 'monte': 'Monte',
            'ehrmann': 'Ehrmann', 'grand dessert': 'Grand Dessert', 'danone': 'Danone',
            'activia': 'Activia', 'actimel': 'Actimel', 'fruchtzwerge': 'Fruchtzwerge', 'froop': 'Froop',
            'barilla': 'Barilla', 'de cecco': 'De Cecco', 'buitoni': 'Buitoni', 'miracoli': 'Mirácoli', 'mirácoli': 'Mirácoli',
            'maggi': 'Maggi', 'knorr': 'Knorr', 'thomy': 'Thomy', 'heinz': 'Heinz', 'kraft': 'Kraft',
            'kühne': 'Kühne', 'hengstenberg': 'Hengstenberg', 'bonduelle': 'Bonduelle', 'erasco': 'Erasco',
            'birkel': 'Birkel', 'mutti': 'Mutti', 'oro di parma': 'Oro di Parma', 'saupiquet': 'Saupiquet', 'appel': 'Appel',
            'tempo': 'Tempo', 'zewa': 'Zewa', 'hakle': 'Hakle', 'ariel': 'Ariel', 'persil': 'Persil',
            'spee': 'Spee', 'lenor': 'Lenor', 'perwoll': 'Perwoll', 'frosch': 'Frosch', 'pril': 'Pril',
            'fairy': 'Fairy', 'somat': 'Somat', 'finish': 'Finish', 'calgon': 'Calgon',
            'meister proper': 'Meister Proper', 'bref': 'Bref', 'cillit bang': 'Cillit Bang', 'domestos': 'Domestos',
            'viss': 'Viss', 'sagrotan': 'Sagrotan', 'nivea': 'Nivea', 'dove': 'Dove', 'palmolive': 'Palmolive',
            'garnier': 'Garnier', 'head & shoulders': 'Head & Shoulders', 'head and shoulders': 'Head & Shoulders',
            'schauma': 'Schauma', 'colgate': 'Colgate', 'blend-a-med': 'Blend-a-med', 'blend a med': 'Blend-a-med',
            'sensodyne': 'Sensodyne', 'elmex': 'Elmex', 'aronal': 'Aronal', 'oral-b': 'Oral-B', 'oral b': 'Oral-B',
            'gillette': 'Gillette', 'wilkinson': 'Wilkinson', 'pampers': 'Pampers'
        })
        
        self.unambiguous_brand_categories = vocab.get('unambiguous_brand_categories', {
            'augustiner': ('Bier', 'Augustiner'), 'krombacher': ('Bier', 'Krombacher'), 'bitburger': ('Bier', 'Bitburger'),
            'warsteiner': ('Bier', 'Warsteiner'), 'becks': ('Bier', "Beck's"), "beck's": ('Bier', "Beck's"),
            'erdinger': ('Bier', 'Erdinger'), 'franziskaner': ('Bier', 'Franziskaner'), 'tegernseer': ('Bier', 'Tegernseer'),
            'rothaus': ('Bier', 'Rothaus'), 'heineken': ('Bier', 'Heineken'), 'corona': ('Bier', 'Corona'),
            'desperados': ('Bier', 'Desperados'), 'astra': ('Bier', 'Astra'), 'jever': ('Bier', 'Jever'),
            'veltins': ('Bier', 'Veltins'), 'hasseröder': ('Bier', 'Hasseröder'), 'oettinger': ('Bier', 'Oettinger'),
            'schöfferhofer': ('Bier', 'Schöfferhofer'), 'flensburger': ('Bier', 'Flensburger'), 'guinness': ('Bier', 'Guinness'),
            'gerolsteiner': ('Mineralwasser', 'Gerolsteiner'), 'volvic': ('Wasser', 'Volvic'), 'vittel': ('Wasser', 'Vittel'),
            'evian': ('Wasser', 'Evian'), 'san pellegrino': ('Mineralwasser', 'San Pellegrino'),
            'adelholzener': ('Mineralwasser', 'Adelholzener'), 'rhönsprudel': ('Mineralwasser', 'RhönSprudel'),
            'apollinaris': ('Mineralwasser', 'Apollinaris'), 'black forest': ('Wasser', 'Black Forest'),
            'coca cola': ('Cola', 'Coca-Cola'), 'coca-cola': ('Cola', 'Coca-Cola'), 'coke zero': ('Cola', 'Coke Zero'),
            'coca cola zero': ('Cola', 'Coca-Cola Zero'), 'pepsi': ('Cola', 'Pepsi'), 'pepsi max': ('Cola', 'Pepsi Max'),
            'fanta': ('Limonade', 'Fanta'), 'sprite': ('Limonade', 'Sprite'), 'mezzo mix': ('Spezi', 'Mezzo Mix'),
            'schwip schwap': ('Spezi', 'Schwip Schwap'), 'paulaner spezi': ('Spezi', 'Paulaner Spezi'),
            'bionade': ('Limonade', 'Bionade'), 'fritz kola': ('Cola', 'Fritz-Kola'), 'fritz-kola': ('Cola', 'Fritz-Kola'),
            'fritz limo': ('Limonade', 'Fritz Limo'), 'club mate': ('Eistee', 'Club-Mate'), 'mio mio mate': ('Eistee', 'Mio Mio Mate'),
            'red bull': ('Energy Drink', 'Red Bull'), 'monster energy': ('Energy Drink', 'Monster Energy'),
            'monster': ('Energy Drink', 'Monster'), 'rockstar': ('Energy Drink', 'Rockstar'), 'effect': ('Energy Drink', 'Effect'),
            'hohes c': ('Saft', 'Hohes C'), 'granini': ('Saft', 'Granini'), 'valensina': ('Saft', 'Valensina'),
            'amecke': ('Saft', 'Amecke'), 'innocent': ('Smoothie', 'Innocent'), 'true fruits': ('Smoothie', 'True Fruits'),
            'lavazza': ('Kaffee', 'Lavazza'), 'dallmayr': ('Kaffee', 'Dallmayr'), 'melitta': ('Kaffee', 'Melitta'),
            'tchibo': ('Kaffee', 'Tchibo'), 'segafredo': ('Kaffee', 'Segafredo'), 'nespresso': ('Kaffeekapseln', 'Nespresso'),
            'senseo': ('Kaffeepads', 'Senseo'), 'dolce gusto': ('Kaffeekapseln', 'Dolce Gusto'),
            'teekanne': ('Tee', 'Teekanne'), 'messmer': ('Tee', 'Meßmer'), 'meßmer': ('Tee', 'Meßmer'),
            'yogi tea': ('Tee', 'Yogi Tea'), 'oatly': ('Hafermilch', 'Oatly'),
            'ritter sport': ('Schokolade', 'Ritter Sport'), 'milka': ('Schokolade', 'Milka'), 'lindt': ('Schokolade', 'Lindt'),
            'ferrero rocher': ('Pralinen', 'Ferrero Rocher'), 'mon cheri': ('Pralinen', 'Mon Chéri'), 'mon chéri': ('Pralinen', 'Mon Chéri'),
            'kinder bueno': ('Schokoriegel', 'Kinder Bueno'), 'kinder riegel': ('Schokoriegel', 'Kinder Riegel'),
            'kinder country': ('Schokoriegel', 'Kinder Country'), 'kinder pingui': ('Milchschnitte', 'Kinder Pingui'),
            'kinder maxi king': ('Milchschnitte', 'Kinder Maxi King'), 'kinder schokolade': ('Schokolade', 'Kinder Schokolade'),
            'raffaello': ('Pralinen', 'Raffaello'), 'giotto': ('Pralinen', 'Giotto'), 'nutella': ('Nutella', ''),
            'duplo': ('Schokoriegel', 'Duplo'), 'hanuta': ('Waffeln', 'Hanuta'), 'toffifee': ('Pralinen', 'Toffifee'),
            'knoppers': ('Waffeln', 'Knoppers'), 'haribo': ('Gummibärchen', 'Haribo'), 'katjes': ('Gummibärchen', 'Katjes'),
            'trolli': ('Gummibärchen', 'Trolli'), 'nimm 2': ('Bonbons', 'Nimm 2'), 'pringles': ('Chips', 'Pringles'),
            'funny frisch': ('Chips', 'Funny-Frisch'), 'funny-frisch': ('Chips', 'Funny-Frisch'), 'chio': ('Chips', 'Chio'),
            'prinzenrolle': ('Kekse', 'Prinzenrolle'), 'oreo': ('Kekse', 'Oreo'), 'kitkat': ('Schokoriegel', 'KitKat'),
            'twix': ('Schokoriegel', 'Twix'), 'snickers': ('Schokoriegel', 'Snickers'), 'mars': ('Schokoriegel', 'Mars'),
            'bounty': ('Schokoriegel', 'Bounty'), 'm&ms': ('Schokolinsen', 'M&Ms'),
            'tempo': ('Taschentücher', 'Tempo'), 'zewa': ('Küchenrollen', 'Zewa'), 'hakle': ('Toilettenpapier', 'Hakle'),
            'pampers': ('Windeln', 'Pampers'), 'persil': ('Waschmittel', 'Persil'), 'ariel': ('Waschmittel', 'Ariel'),
            'spee': ('Waschmittel', 'Spee'), 'perwoll': ('Waschmittel', 'Perwoll'), 'lenor': ('Weichspüler', 'Lenor'),
            'pril': ('Spülmittel', 'Pril'), 'fairy': ('Spülmittel', 'Fairy'), 'somat': ('Spülmaschinentabs', 'Somat'),
            'finish': ('Spülmaschinentabs', 'Finish'), 'calgon': ('Wasserenthärter', 'Calgon'),
            'meister proper': ('Allzweckreiniger', 'Meister Proper'), 'sagrotan': ('Desinfektionsmittel', 'Sagrotan'),
            'head & shoulders': ('Shampoo', 'Head & Shoulders'), 'schauma': ('Shampoo', 'Schauma'),
            'colgate': ('Zahnpasta', 'Colgate'), 'blend-a-med': ('Zahnpasta', 'Blend-a-med'),
            'sensodyne': ('Zahnpasta', 'Sensodyne'), 'elmex': ('Zahnpasta', 'Elmex'), 'gillette': ('Rasierklingen', 'Gillette')
        })
        
        self.bring_canonical_synonyms = vocab.get('bring_canonical_synonyms', {
            'geriebener käse': ('Käse', 'gerieben'), 'geriebener kase': ('Käse', 'gerieben'),
            'käse gerieben': ('Käse', 'gerieben'), 'kase gerieben': ('Käse', 'gerieben'),
            'streukäse': ('Käse', 'gerieben'), 'gratinkäse': ('Käse', 'gerieben'),
            'geriebener gouda': ('Käse', 'Gouda gerieben'), 'geriebener mozzarella': ('Mozzarella', 'gerieben'),
            'geriebener parmesan': ('Parmesan', 'gerieben'), 'toastbrot': ('Toast', ''),
            'spülmaschinentabs': ('Geschirrtabs', ''), 'geschirrspültabs': ('Geschirrtabs', ''),
            'müllbeutel': ('Müllsäcke', ''), 'mülltüten': ('Müllsäcke', ''),
            'paniermehl': ('Semmelbrösel', ''), 'gehackte tomaten': ('Dosentomaten', ''),
            'stückige tomaten': ('Dosentomaten', ''), 'pelati': ('Dosentomaten', ''),
            'schlagsahne': ('Sahne', ''), 'schmand': ('Sauerrahm', '')
        })
        
        self.cat_head_nouns = vocab.get('cat_head_nouns', {
            'kekse': 'Kekse', 'keks': 'Kekse', 'cookies': 'Kekse', 'cookie': 'Kekse',
            'joghurt': 'Joghurt', 'joghurts': 'Joghurt', 'milch': 'Milch', 'butter': 'Butter',
            'brot': 'Brot', 'brote': 'Brot', 'brötchen': 'Brötchen', 'broetchen': 'Brötchen', 'semmeln': 'Brötchen', 'wecken': 'Brötchen',
            'mehl': 'Mehl', 'nudeln': 'Nudeln', 'spaghetti': 'Spaghetti', 'penne': 'Penne',
            'käse': 'Käse', 'kase': 'Käse', 'schokolade': 'Schokolade', 'chips': 'Chips',
            'saft': 'Saft', 'säfte': 'Saft', 'saefte': 'Saft', 'tee': 'Tee', 'tees': 'Tee',
            'öl': 'Öl', 'oel': 'Öl', 'speiseöl': 'Öl', 'speiseoel': 'Öl',
            'marmelade': 'Marmelade', 'konfitüre': 'Marmelade', 'konfituere': 'Marmelade',
            'müsli': 'Müsli', 'muesli': 'Müsli', 'essig': 'Essig', 'senf': 'Senf', 'ketchup': 'Ketchup',
            'quark': 'Quark', 'sahne': 'Sahne', 'reis': 'Reis', 'fleisch': 'Fleisch',
            'wurst': 'Wurst', 'würstchen': 'Würstchen', 'wuerstchen': 'Würstchen', 'schinken': 'Schinken',
            'suppe': 'Suppe', 'suppen': 'Suppe', 'sauce': 'Sauce', 'soße': 'Sauce', 'sosse': 'Sauce',
            'eis': 'Eis', 'speiseeis': 'Eis'
        })
        
        self.compound_protected_items = set(vocab.get('compound_protected_items', [
            'kräuterbutter', 'kraeuterbutter', 'frischkäse', 'frischkase', 'tomatenmark',
            'hackfleisch', 'kochschinken', 'bratwurst', 'currywurst', 'leberwurst',
            'apfelsaft', 'orangensaft', 'olivenöl', 'olivenoel', 'sauerkraut', 'rotkohl',
            'kartoffelsalat', 'nudelsalat', 'eiersalat', 'fleischsalat', 'backpulver',
            'vanillezucker', 'puderzucker', 'roggenbrot', 'vollkornbrot', 'toastbrot'
        ]))
        
        self.brand_pairs = {k for k in self.brand_map.keys() if ' ' in k}

        self.units_list = [
            'kg', 'kilo', 'kilogramm', 'g', 'gramm', 'l', 'liter', 'ml', 'milliliter', 'cl', 'dl',
            'qm', 'quadratmeter', 'meter', 'm', 'zentimeter', 'centimeter', 'cm', 'millimeter', 'mm', 'zoll',
            'packung', 'packungen', 'pkg', 'pack', 'packs', 'pck', 'paket', 'pakete',
            'stk', 'stück', 'flasche', 'flaschen', 'dose', 'dosen', 'bund', 'bunt',
            'beutel', 'glas', 'gläser', 'scheibe', 'scheiben', 'kasten', 'kästen', 'kiste', 'kisten',
            'tüte', 'tüten', 'becher', 'zehe', 'zehen', 'knolle', 'knollen', 'tafel', 'tafeln',
            'tube', 'tuben', 'kartusche', 'kartuschen', 'stange', 'stangen', 'zweig', 'zweige',
            'rolle', 'rollen', 'karton', 'kartons', 'portion', 'portionen', 'paar',
            'schale', 'schalen', 'netz', 'netze', 'steige', 'steigen', 'sack', 'säcke',
            'eimer', 'kanister', 'bogen', 'blatt', 'latte', 'latten', 'leiste', 'leisten',
            'brett', 'bretter', 'platte', 'platten', '%', 'prozent'
        ]
        self.units_pattern = '|'.join(sorted(self.units_list, key=len, reverse=True))

        self.noun_units = {
            'kiste': 'Kiste', 'kisten': 'Kisten', 'kasten': 'Kasten', 'kästen': 'Kästen',
            'bund': 'Bund', 'bunt': 'Bund', 'packung': 'Packung', 'packungen': 'Packungen',
            'pkg': 'Pkg.', 'pack': 'Pack', 'packs': 'Packs', 'pck': 'Pck.', 'paket': 'Paket', 'pakete': 'Pakete',
            'flasche': 'Flasche', 'flaschen': 'Flaschen', 'dose': 'Dose', 'dosen': 'Dosen',
            'beutel': 'Beutel', 'glas': 'Glas', 'gläser': 'Gläser', 'scheibe': 'Scheibe', 'scheiben': 'Scheiben',
            'tüte': 'Tüte', 'tüten': 'Tüten', 'becher': 'Becher', 'zehe': 'Zehe', 'zehen': 'Zehen',
            'knolle': 'Knolle', 'knollen': 'Knollen', 'tafel': 'Tafel', 'tafeln': 'Tafeln',
            'tube': 'Tube', 'tuben': 'Tuben', 'kartusche': 'Kartusche', 'kartuschen': 'Kartuschen',
            'stange': 'Stange', 'stangen': 'Stangen', 'zweig': 'Zweig', 'zweige': 'Zweige',
            'rolle': 'Rolle', 'rollen': 'Rollen', 'karton': 'Karton', 'kartons': 'Kartons',
            'portion': 'Portion', 'portionen': 'Portionen', 'paar': 'Paar',
            'schale': 'Schale', 'schalen': 'Schalen', 'netz': 'Netz', 'netze': 'Netze',
            'steige': 'Steige', 'steigen': 'Steigen', 'sack': 'Sack', 'säcke': 'Säcke',
            'eimer': 'Eimer', 'kanister': 'Kanister', 'stück': 'Stück', 'stk': 'Stück', 'zoll': 'Zoll'
        }
        
        self.beverage_brands = {
            'fanta', 'sprite', 'cola', 'coca cola', 'coca-cola', 'coke zero', 'coca cola zero',
            'pepsi', 'pepsi max', 'spezi', 'mezzo mix', 'schwip schwap', 'paulaner spezi',
            'bionade', 'fritz kola', 'fritz-kola', 'fritz limo', 'club mate', 'mio mio', 'mio mio mate',
            'red bull', 'monster energy', 'monster', 'rockstar', 'effect',
            'gerolsteiner', 'volvic', 'vittel', 'evian', 'san pellegrino', 'adelholzener', 'apollinaris', 'rhönsprudel',
            'hohes c', 'granini', 'valensina', 'innocent', 'true fruits', 'pfanner', 'amecke',
            'krombacher', 'bitburger', 'warsteiner', 'becks', 'paulaner', 'erdinger', 'augustiner', 'tegernseer'
        }
        
        self.beverage_nouns = {
            'limonade', 'limo', 'cola', 'spezi', 'bier', 'pils', 'weizen', 'helles', 'dunkles',
            'wasser', 'mineralwasser', 'sprudel', 'saft', 'eistee', 'energy drink', 'energydrink',
            'getränk', 'kasten', 'kiste', 'flasche', 'flaschen', 'dose', 'dosen', 'sixpack', 'träger', 'alkoholfreies bier'
        }
        
        self.grain_style_prefixes = ['vollkorn', 'dinkel', 'roggen', 'weizen', 'hartweizen', 'glutenfrei', 'glutenfreie', 'glutenfreies']
        self.known_grain_nouns = {
            'spaghetti', 'nudeln', 'penne', 'brot', 'toast', 'mehl', 'reis', 'grieß', 'haferflocken', 'brötchen', 'kekse', 'waffeln', 'teig', 'wraps'
        }

    async def async_update_vocab(self, session, cache_dir: str):
        """Fetch updated vocab from GitHub if cache is older than 24 hours."""
        cache_file = os.path.join(cache_dir, "bring_vocab_cache.json")
        
        # Check cache age
        if os.path.exists(cache_file):
            file_age = time.time() - os.path.getmtime(cache_file)
            if file_age < CACHE_EXPIRY_SECONDS:
                _LOGGER.debug("Vocab cache is fresh enough. Loading from cache.")
                try:
                    def _load_vocab():
                        with open(cache_file, 'r', encoding='utf-8') as f:
                            return json.load(f)
                    cached_vocab = await asyncio.to_thread(_load_vocab)
                    self.__init__(cached_vocab)
                    return
                except Exception as e:
                    _LOGGER.warning("Could not read vocab cache: %s", str(e))
        
        # Fetch from GitHub
        _LOGGER.info("Fetching updated Bring! vocab from GitHub OTA...")
        try:
            async with session.get(OTA_VOCAB_URL) as resp:
                if resp.status == 200:
                    new_vocab = await resp.json(content_type=None)
                    if new_vocab and isinstance(new_vocab, dict):
                        def _save_vocab():
                            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                            with open(cache_file, 'w', encoding='utf-8') as f:
                                json.dump(new_vocab, f, ensure_ascii=False)
                        await asyncio.to_thread(_save_vocab)
                        self.__init__(new_vocab)
                        _LOGGER.info("Successfully updated Bring! vocab OTA.")
                    else:
                        _LOGGER.warning("Invalid JSON structure fetched from OTA.")
                else:
                    _LOGGER.warning("Failed to fetch vocab OTA (HTTP %s). Using defaults.", resp.status)
        except Exception as e:
            _LOGGER.warning("Error fetching vocab OTA: %s. Using defaults.", str(e))

    def _stem_german(self, word: str) -> str:
        w = word.lower().strip()
        w = w.replace('ä', 'a').replace('ö', 'o').replace('ü', 'u').replace('ß', 'ss')
        if len(w) >= 4:
            w = re.sub(r'(?:en|ern|er|e|s|n)$', '', w)
        return w

    def normalize_spoken_german(self, text: str) -> str:
        t = text.strip()
        t = re.sub(r'\bnull\b', '0', t, flags=re.IGNORECASE)

        fraction_map = [
            (r'\banderthalb\b|\beineinhalb\b', '1.5'), (r'\bzweieinhalb\b', '2.5'), (r'\bdreieinhalb\b', '3.5'),
            (r'\bviereinhalb\b', '4.5'), (r'\bfünfeinhalb\b', '5.5'), (r'\bdreiviertel\b|\bdrei\s*viertel\b', '0.75'),
            (r'(?:\bein\s+)?halbes\s+dutzend\b', '6'), (r'(?:\bein\s+)?dutzend\b', '12'),
            (r'(?:\bein\s+)?halbes\s+pfund\b', '250g'), (r'(?:\bein\s+)?pfund\b', '500g'),
            (r'(?:\bein\s+)?halbes\b|(?:\bein\s+)?halber\b|(?:\bein\s+)?halb\b|(?:\beine\s+)?halbe\b', '0.5'),
            (r'(?:\bein\s+)?viertel\b', '0.25')
        ]
        for pattern, val in fraction_map:
            t = re.sub(pattern, val, t, flags=re.IGNORECASE)

        hundred_prefixes = {'ein': 100, 'zwei': 200, 'drei': 300, 'vier': 400, 'fünf': 500, 'sechs': 600, 'sieben': 700, 'acht': 800, 'neun': 900}
        for h_name, h_val in hundred_prefixes.items():
            t = re.sub(rf'\b{h_name}\s*hundert', f'{h_val} ', t, flags=re.IGNORECASE)
        t = re.sub(r'\bhundert\b', '100 ', t, flags=re.IGNORECASE)
        t = re.sub(r'\btausend\b', '1000 ', t, flags=re.IGNORECASE)

        ones = {'ein': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9}
        tens = {'zwanzig': 20, 'dreißig': 30, 'vierzig': 40, 'fünfzig': 50, 'sechzig': 60, 'siebzig': 70, 'achtzig': 80, 'neunzig': 90}
        for one_k, one_v in ones.items():
            for ten_k, ten_v in tens.items():
                compound = f"{one_k}und{ten_k}"
                total = one_v + ten_v
                t = re.sub(rf'\b{compound}\b', str(total), t, flags=re.IGNORECASE)

        word_to_num = {
            'zwanzig': '20', 'dreißig': '30', 'vierzig': '40', 'fünfzig': '50', 'sechzig': '60', 'siebzig': '70', 'achtzig': '80', 'neunzig': '90',
            'dreizehn': '13', 'vierzehn': '14', 'fünfzehn': '15', 'sechzehn': '16', 'siebzehn': '17', 'achtzehn': '18', 'neunzehn': '19',
            'zwölf': '12', 'elf': '11', 'zehn': '10', 'neun': '9', 'acht': '8', 'sieben': '7', 'sechs': '6', 'fünf': '5', 'vier': '4', 'drei': '3', 'zwei': '2',
            'eins': '1', 'eine': '1', 'einen': '1', 'einem': '1', 'einer': '1', 'ein': '1'
        }
        for w, n in word_to_num.items():
            t = re.sub(rf'\b{w}\b', str(n), t, flags=re.IGNORECASE)

        t = re.sub(r'\b(\d{1,4}00)\s+(\d{1,2})\b', lambda m: str(int(m.group(1)) + int(m.group(2))), t)
        t = re.sub(r'\b(\d+)\s*(?:komma|punkt|,|\.)\s*(\d+)\b', r'\1.\2', t, flags=re.IGNORECASE)

        t = re.sub(r'\bdoktor\s+oetker\b', 'Dr. Oetker', t, flags=re.IGNORECASE)
        t = re.sub(r'\bdr\s+oetker\b', 'Dr. Oetker', t, flags=re.IGNORECASE)
        t = re.sub(r'\bgusto\s+gustavo\b', 'Gustavo Gusto', t, flags=re.IGNORECASE)
        t = re.sub(r'\bben\s+(?:und|and|&)\s+jerrys\b', 'Ben and Jerrys', t, flags=re.IGNORECASE)
        t = re.sub(r'\bhäagen\s+dazs\b|\bhaagen\s+dazs\b', 'Haagen Dazs', t, flags=re.IGNORECASE)
        t = re.sub(r'\bmilch\s+schnitte\b', 'Milchschnitte', t, flags=re.IGNORECASE)

        return t.strip()

    def strip_command_phrases(self, text: str) -> str:
        t = text.strip()
        for qp in [
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:änder(?:e)?|korrigier(?:e)?|erhöh(?:e)?|setz(?:e)?|pass(?:e)?)\s+(?:(?:die\s+)?(?:menge|anzahl)\s*(?:von|der)?\s+)?(.+?)\s+(?:auf|zu|in|an)\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?mach\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)\s+(.+?)\s+draus$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?mach\s+aus\s+(.+?)\s+(\d+(?:[.,]\d+)?(?:\s*[a-zA-ZäöüÄÖÜß]+)?)$',
        ]:
            qm = re.match(qp, t, re.IGNORECASE)
            if qm:
                g1, g2 = qm.group(1).strip(), qm.group(2).strip()
                if re.match(r'^\d', g1):
                    qty, item = g1, g2
                else:
                    item, qty = g1, g2
                item = re.sub(r'^(?:die|das|der|den|dem|meine|unsere)\s+', '', item, flags=re.IGNORECASE).strip()
                return f"{qty} {item}"

        patterns = [
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?|streich(?:e)?)\s+(.+?)\s+(?:von|aus|von\s+der|von\s+den|von\s+unserer|von\s+meiner)\s+(?:der|meiner|unserer|den|die)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:nimm|tu)\s+(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s*runter$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:lösch(?:e)?|entfern(?:e)?|streich(?:e)?)\s+(.+)$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:von|aus)\s+(?:der|den|meiner|unserer)\s+(?:einkaufsliste|liste|zettel)\s+(?:löschen|entfernen|streichen|runternehmen)$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:löschen|entfernen|streichen|abhaken)$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:auf|zu|zur|in|an)\s+(?:die|meine|unsere|den|der|das|meinen|unseren)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)\s*(?:schreiben|setzen|packen|hinzufügen|draufpacken|draufsetzen|drauftun)$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(.+?)\s+(?:hinzufügen|dazuschreiben|draufpacken|draufsetzen)$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|für|tu|pack)\s+(?:bitte\s+)?(?:noch\s+)?(.+?)\s+(?:auf|zu|zur|in|an|der)\s+(?:die|meine|unsere|den|der|das|meinen|unseren)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf)?$',
            r'^(?:alexa,?\s*)?(?:bitte\s*)?(?:wir\s+brauchen\s+noch|kauf\s+bitte|kauf(?:en)?|besorg(?:e)?)\s+(.+)$',
            r'^(?:alexa,?\s*)?(?:sag|sage|frage|öffne)\s+(?:meinem?\s+)?(?:einkaufszettel|einkaufsliste|bring|liste)(?::|\s+)?\s*(.+)$',
            r'^(?:setz(?:e)?|pack(?:e)?|schreib(?:e)?|füg(?:e)?|für|tu)\s+(?:bitte\s+)?(?:noch\s+)?(.+?)(?:\s+(?:auf|zu|zur|in|der)\s+(?:die|den|meine|unsere|der|das|meinen)\s+(?:einkaufsliste|liste|zettel))?$'
        ]
        for p in patterns:
            m = re.match(p, t, re.IGNORECASE)
            if m:
                t = m.group(1)
                break
        t = re.sub(r'^(?:alexa,?\s*)?(?:noch|bitte|mal|eben|schnell)\s+', '', t, flags=re.IGNORECASE)
        t = re.sub(r'\s+(?:auf|zu|zur|in|an|der|den|die|das|meine|unsere|meinen)?\s*(?:die|meine|unsere|den|der|das|meinen)?\s*(?:einkaufsliste|einkaufszettel|liste|zettel|bring(?:\s*liste)?)(?:\s*hinzu|\s*drauf|\s*ab)?$', '', t, flags=re.IGNORECASE)
        t = re.sub(r'\s+(?:zur|zu|auf|an|für|hinzu|drauf|runter|weg|bitte|danke|noch|löschen|entfernen|streichen|schreiben|packen|setzen)$', '', t, flags=re.IGNORECASE)
        return t.strip()

    def format_specification(self, spec_str: str) -> str:
        if not spec_str:
            return ''
        s = spec_str.strip()
        s = re.sub(r'(\d+(?:\.\d+)?)\s*gramm\b', r'\1g', s, flags=re.IGNORECASE)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*kilo(?:gramm)?\b', r'\1kg', s, flags=re.IGNORECASE)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*milliliter\b', r'\1ml', s, flags=re.IGNORECASE)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*liter\b', r'\1l', s, flags=re.IGNORECASE)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*meter\b', r'\1m', s, flags=re.IGNORECASE)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*(?:zentimeter|centimeter)\b', r'\1cm', s, flags=re.IGNORECASE)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*millimeter\b', r'\1mm', s, flags=re.IGNORECASE)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*quadratmeter\b', r'\1qm', s, flags=re.IGNORECASE)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*prozent\b', r'\1%', s, flags=re.IGNORECASE)

        words = s.split()
        formatted_words = []
        for w in words:
            w_low = w.lower()
            if w_low in self.noun_units:
                formatted_words.append(self.noun_units[w_low])
            else:
                formatted_words.append(w)
        return " ".join(formatted_words)

    def extract_specification(self, text: str) -> tuple[str, str]:
        t = text.strip()
        t = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', t, flags=re.IGNORECASE).strip()

        pattern_unit = rf'^\s*(\d+(?:[.,]\d+)?\s*(?:{self.units_pattern}))\s+(?:von\s+(?:den|der|dem|meinen)?\s*)?(.+)$'
        m = re.match(pattern_unit, t, re.IGNORECASE)
        if m:
            spec = self.format_specification(m.group(1).strip())
            name = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', m.group(2).strip(), flags=re.IGNORECASE).strip()
            return name, spec

        pattern_plain = r'^\s*(\d+(?:[.,]\d+)?)\s+(?:von\s+(?:den|der|dem)?\s*)?([a-zA-ZäöüÄÖÜß].+)$'
        m = re.match(pattern_plain, t, re.IGNORECASE)
        if m:
            spec = m.group(1).strip()
            name = re.sub(r'^(?:die|das|der|den|dem|des|ein|eine|einen|einem|einer)\s+', '', m.group(2).strip(), flags=re.IGNORECASE).strip()
            return name, spec

        pattern_end_unit = rf'^(.+?)\s+(\d+(?:[.,]\d+)?\s*(?:{self.units_pattern}))$'
        m = re.match(pattern_end_unit, t, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            spec = self.format_specification(m.group(2).strip())
            return name, spec

        pattern_end_plain = r'^([a-zA-ZäöüÄÖÜß\s\.\&\-\']+?)\s+(\d+(?:[.,]\d+)?)$'
        m = re.match(pattern_end_plain, t, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            spec = m.group(2).strip()
            return name, spec

        return t, ''

    def decompose_grain_style(self, q_low: str, existing_spec: str = '') -> tuple[str, str]:
        for prefix in sorted(self.grain_style_prefixes, key=len, reverse=True):
            rest = None
            if q_low.startswith(prefix + " "):
                rest = q_low[len(prefix) + 1:].strip()
            elif q_low.startswith(prefix) and len(q_low) > len(prefix):
                rest = q_low[len(prefix):].strip()

            if rest and (rest in self.known_grain_nouns or len(rest) >= 4):
                spec_add = prefix.capitalize()
                spec = f"{existing_spec} {spec_add}".strip() if existing_spec else spec_add
                return rest, spec
        return q_low, existing_spec

    def decompose_compound_item(self, word: str, existing_spec: str = '') -> tuple[str, str]:
        w_low = word.lower().strip()
        if w_low in self.compound_protected_items or ' ' in w_low:
            return word, existing_spec

        for suffix, target_cat in sorted(self.cat_head_nouns.items(), key=lambda x: len(x[0]), reverse=True):
            if w_low.endswith(suffix) and len(w_low) > len(suffix) + 2:
                prefix = w_low[:-len(suffix)].strip()
                if prefix.endswith('en') and len(prefix) > 4:
                    prefix_clean = prefix[:-1]
                elif prefix.endswith('s') and len(prefix) > 4:
                    prefix_clean = prefix[:-1]
                else:
                    prefix_clean = prefix

                brand_match = self.brand_map.get(prefix) or self.brand_map.get(prefix_clean)
                spec_add = brand_match if brand_match else prefix_clean.capitalize()
                spec = f"{existing_spec} {spec_add}".strip() if existing_spec else spec_add
                return target_cat, spec

        return word, existing_spec

    def extract_brand_item(self, query_name: str, existing_spec: str = '') -> tuple[str, str]:
        q_low = query_name.lower().strip()

        m_gerieben = re.match(r'^geriebene[rnse]?\s+(.+)$', q_low)
        if m_gerieben:
            item_part = m_gerieben.group(1).strip()
            cheese_types = {'gouda', 'emmentaler', 'cheddar', 'bergkäse', 'edamer', 'tilsiter', 'butterkäse', 'manchego', 'pecorino'}
            if item_part in ['käse', 'kase']:
                spec = f"{existing_spec} gerieben".strip() if existing_spec else "gerieben"
                return 'Käse', spec
            elif item_part in cheese_types:
                spec_text = f"{item_part.capitalize()} gerieben"
                spec = f"{existing_spec} {spec_text}".strip() if existing_spec else spec_text
                return 'Käse', spec
            elif item_part in ['mozzarella', 'parmesan']:
                spec = f"{existing_spec} gerieben".strip() if existing_spec else "gerieben"
                return item_part.capitalize(), spec
            else:
                spec = f"{existing_spec} gerieben".strip() if existing_spec else "gerieben"
                return item_part.capitalize(), spec

        if q_low in self.bring_canonical_synonyms:
            canon_name, canon_spec = self.bring_canonical_synonyms[q_low]
            combined_spec = f"{existing_spec} {canon_spec}".strip() if existing_spec else canon_spec
            return canon_name, combined_spec

        matched_brand = False
        cur_name = query_name
        cur_spec = existing_spec
        for brand_key in sorted(self.brand_map.keys(), key=len, reverse=True):
            brand_display = self.brand_map[brand_key]
            if q_low.startswith(brand_key):
                remainder = q_low[len(brand_key):].strip()
                if remainder and len(remainder) >= 2:
                    cur_name = " ".join([w.capitalize() for w in remainder.split()])
                    cur_spec = f"{existing_spec} {brand_display}".strip() if existing_spec else brand_display
                    matched_brand = True
                    break
            elif q_low.endswith(brand_key):
                noun_part = q_low[:-len(brand_key)].strip()
                if noun_part and len(noun_part) >= 2:
                    cur_name = " ".join([w.capitalize() for w in noun_part.split()])
                    cur_spec = f"{existing_spec} {brand_display}".strip() if existing_spec else brand_display
                    matched_brand = True
                    break

        if not matched_brand and q_low in self.unambiguous_brand_categories:
            cat_name, brand_display = self.unambiguous_brand_categories[q_low]
            combined_spec = f"{existing_spec} {brand_display}".strip() if existing_spec else brand_display
            return cat_name, combined_spec

        if not matched_brand and q_low in self.brand_map:
            return self.brand_map[q_low], existing_spec

        n_low = cur_name.lower().strip()
        if n_low in self.bring_canonical_synonyms:
            canon_name, canon_spec = self.bring_canonical_synonyms[n_low]
            combined_spec = f"{cur_spec} {canon_spec}".strip() if cur_spec else canon_spec
            return canon_name, combined_spec

        decomp_rest, decomp_spec = self.decompose_grain_style(n_low, cur_spec)
        if decomp_rest != n_low:
            cap_name = " ".join([w.capitalize() for w in decomp_rest.split()])
            return cap_name, decomp_spec

        comp_name, comp_spec = self.decompose_compound_item(n_low, cur_spec)
        if comp_name.lower() != n_low:
            return comp_name, comp_spec

        return cur_name, cur_spec

    def is_brand_token(self, token: str) -> bool:
        tok = token.lower().strip()
        return any(k == tok or k.startswith(tok + ' ') for k in self.brand_map.keys()) or tok in self.unambiguous_brand_categories or tok in ['cola', 'fanta', 'sprite', 'spezi', 'bier', 'wasser']

    def is_brand_extension(self, words: list[str], i: int) -> tuple[int, str]:
        w_low = words[i].lower().strip()

        if i + 4 < len(words):
            tri = f"{w_low} {words[i+1].lower()} {words[i+2].lower()}"
            next_tok = words[i+4].lower().strip()
            if tri in self.brand_map and words[i+3].lower() in self.grocery_adjectives and not self.is_brand_token(words[i+4]) and not re.match(r'^\d', next_tok) and next_tok not in self.units_list:
                return 5, f"{words[i]} {words[i+1]} {words[i+2]} {words[i+3]} {words[i+4]}"

        if i + 3 < len(words):
            tri = f"{w_low} {words[i+1].lower()} {words[i+2].lower()}"
            next_tok = words[i+3].lower().strip()
            if tri in self.brand_map and not self.is_brand_token(words[i+3]) and not re.match(r'^\d', next_tok) and next_tok not in self.units_list:
                return 4, f"{words[i]} {words[i+1]} {words[i+2]} {words[i+3]}"

        if i + 3 < len(words):
            pair = f"{w_low} {words[i+1].lower()}"
            next_tok = words[i+3].lower().strip()
            if pair in self.brand_map and words[i+2].lower() in self.grocery_adjectives and not self.is_brand_token(words[i+3]) and not re.match(r'^\d', next_tok) and next_tok not in self.units_list:
                return 4, f"{words[i]} {words[i+1]} {words[i+2]} {words[i+3]}"

        if i + 2 < len(words):
            pair = f"{w_low} {words[i+1].lower()}"
            next_tok = words[i+2].lower().strip()
            if pair in self.brand_map and not self.is_brand_token(words[i+2]) and not re.match(r'^\d', next_tok) and next_tok not in self.units_list:
                return 3, f"{words[i]} {words[i+1]} {words[i+2]}"

        if i + 2 < len(words):
            next_tok = words[i+2].lower().strip()
            if w_low in self.brand_map and words[i+1].lower() in self.grocery_adjectives and not self.is_brand_token(words[i+2]) and not re.match(r'^\d', next_tok) and next_tok not in self.units_list:
                return 3, f"{words[i]} {words[i+1]} {words[i+2]}"

        if i + 1 < len(words):
            next_tok = words[i+1].lower().strip()
            if w_low in self.brand_map and not self.is_brand_token(words[i+1]) and not re.match(r'^\d', next_tok) and next_tok not in self.units_list:
                if w_low in self.beverage_brands:
                    if next_tok in self.beverage_nouns or next_tok in self.units_list:
                        return 2, f"{words[i]} {words[i+1]}"
                else:
                    return 2, f"{words[i]} {words[i+1]}"

        if i + 2 < len(words):
            tri = f"{w_low} {words[i+1].lower()} {words[i+2].lower()}"
            if tri in self.standalone_products or tri in self.brand_map:
                return 3, f"{words[i]} {words[i+1]} {words[i+2]}"

        if i + 1 < len(words):
            pair = f"{w_low} {words[i+1].lower()}"
            if pair in self.standalone_products or pair in self.brand_map:
                return 2, f"{words[i]} {words[i+1]}"

        return 0, ""

    def is_multiword_pair(self, w1: str, w2: str, catalog_names: list[str]) -> bool:
        low1, low2 = w1.lower().strip(), w2.lower().strip()
        full_space = f"{low1} {low2}"
        full_compound = f"{low1}{low2}"

        for cat in catalog_names:
            clow = cat.lower()
            if clow == full_space or clow == full_compound:
                return True

        if full_space in self.foreign_terms or full_compound in self.foreign_terms or full_space in self.brand_pairs or full_compound in self.brand_pairs:
            return True

        if full_compound in self.valid_base_compounds or full_space in self.valid_base_compounds:
            return True

        if re.match(r'^\d+er$', low1):
            return True

        if low1 in self.grocery_adjectives:
            return True

        if low2 in self.dependent_suffixes:
            return True

        is_distinct = any(cat.lower() == low2 or cat.lower().replace(" ", "") == low2 for cat in catalog_names)
        if low1 in self.compound_prefixes and not is_distinct:
            if full_compound in self.valid_base_compounds or low2 in self.dependent_suffixes:
                return True
            if low1 in {'puten', 'rinder', 'schweine', 'hähnchen', 'hafer', 'mandel', 'soja', 'kokos', 'vanille', 'puder', 'back'}:
                return True

        return False

    def split_compound_of_known_items(self, word: str, catalog_names: list[str]) -> list[str]:
        w_low = word.lower().strip()
        for cat in catalog_names:
            clow = cat.lower()
            if clow == w_low or clow.replace(" ", "") == w_low:
                return [word]
        if w_low in self.valid_base_compounds or w_low.replace(" ", "") in self.valid_base_compounds:
            return [word]
        if w_low in self.foreign_terms or w_low.replace(" ", "") in self.foreign_terms or w_low in self.brand_pairs or w_low.replace(" ", "") in self.brand_pairs:
            return [word]

        for cat1 in catalog_names:
            c1_low = cat1.lower()
            if len(c1_low) >= 3 and w_low.startswith(c1_low):
                remainder = w_low[len(c1_low):].strip()
                if remainder in self.cat_head_nouns:
                    return [word]
                for cat2 in catalog_names:
                    c2_low = cat2.lower()
                    if remainder == c2_low:
                        return [cat1, cat2]
        return [word]

    def smart_split_consecutive(self, text: str, catalog_names: list[str]) -> list[str]:
        t = text.strip()
        words = t.split()
        if len(words) <= 1:
            return self.split_compound_of_known_items(t, catalog_names)

        low = t.lower()
        for cat in catalog_names:
            clow = cat.lower()
            if clow == low or clow == low.replace(" ", ""):
                return [t]
        if low in self.foreign_terms or low.replace(" ", "") in self.foreign_terms or low in self.brand_map or low in self.standalone_products:
            return [t]

        for b in self.brand_map.keys():
            if (low.startswith(b + ' ') and low[len(b)+1:].strip() in [c.lower() for c in catalog_names]) or \
               (low.endswith(' ' + b) and low[:-len(b)-1].strip() in [c.lower() for c in catalog_names]):
                return [t]

        for gp in self.grain_style_prefixes:
            if (low.startswith(gp) and low[len(gp):].strip() in self.known_grain_nouns) or \
               (low.endswith(gp) and low[:-len(gp)].strip() in self.known_grain_nouns):
                return [t]

        results = []
        i = 0
        while i < len(words):
            w = words[i]
            w_low = w.lower()

            if re.match(rf'^\d+(?:[.,]\d+)?(?:{self.units_pattern})$', w_low):
                if i + 1 < len(words):
                    rem_phrase = " ".join(words[i+1:])
                    sub_parsed = self.smart_split_consecutive(rem_phrase, catalog_names)
                    if sub_parsed:
                        results.append(f"{w} {sub_parsed[0]}")
                        results.extend(sub_parsed[1:])
                    else:
                        results.append(w)
                    break

            if re.match(r'^\d+(?:[.,]\d+)?$', w_low):
                if i + 2 < len(words) and words[i+1].lower() in self.units_list:
                    rem_phrase = " ".join(words[i+2:])
                    sub_parsed = self.smart_split_consecutive(rem_phrase, catalog_names)
                    if sub_parsed:
                        results.append(f"{w} {words[i+1]} {sub_parsed[0]}")
                        results.extend(sub_parsed[1:])
                    else:
                        results.append(f"{w} {words[i+1]}")
                    break
                elif i + 1 < len(words):
                    rem_phrase = " ".join(words[i+1:])
                    sub_parsed = self.smart_split_consecutive(rem_phrase, catalog_names)
                    if sub_parsed:
                        results.append(f"{w} {sub_parsed[0]}")
                        results.extend(sub_parsed[1:])
                    else:
                        results.append(f"{w}")
                    break

            consumed, brand_phrase = self.is_brand_extension(words, i)
            if consumed > 0:
                rem = words[i+consumed:]
                if len(rem) >= 2 and re.match(r'^\d+(?:[.,]\d+)?$', rem[0].lower()) and rem[1].lower() in self.units_list:
                    results.append(f"{brand_phrase} {rem[0]} {rem[1]}")
                    i += consumed + 2
                    continue
                results.append(brand_phrase)
                i += consumed
                continue

            if i + 1 < len(words):
                next_w = words[i + 1]
                if self.is_multiword_pair(w, next_w, catalog_names):
                    results.append(f"{w} {next_w}")
                    i += 2
                    continue

            rem = words[i+1:]
            if len(rem) >= 2 and re.match(r'^\d+(?:[.,]\d+)?$', rem[0].lower()) and rem[1].lower() in self.units_list:
                results.append(f"{w} {rem[0]} {rem[1]}")
                i += 3
                continue

            results.append(w)
            i += 1

        return results

    def match_catalog_name(self, query_name: str, catalog_names: list[str]) -> str:
        q_clean = query_name.strip()
        q_low = q_clean.lower()
        q_compound = q_low.replace(" ", "")
        q_stem = self._stem_german(q_low)

        for cat in catalog_names:
            if cat.lower() == q_low:
                return cat

        for cat in catalog_names:
            if cat.lower().replace(" ", "") == q_compound:
                return cat

        if len(q_stem) >= 3 and " " not in q_low:
            for cat in catalog_names:
                c_stem = self._stem_german(cat)
                if c_stem == q_stem:
                    return cat

        if q_low in self.foreign_terms or q_compound in self.foreign_terms:
            words = [w.capitalize() for w in q_clean.split()]
            return " ".join(words)

        words = q_clean.split()
        if len(words) == 2:
            w1_low = words[0].lower()
            if re.match(r'^\d+er$', w1_low):
                return f"{words[0]} {words[1].capitalize()}"
            if w1_low in self.grocery_adjectives:
                return f"{words[0].capitalize()} {words[1].capitalize()}"
            return f"{words[0].capitalize()}{words[1].lower()}"

        res_words = [w.capitalize() for w in words]
        return " ".join(res_words)

    def is_valid_grocery_item(self, name: str, catalog_names: list[str]) -> bool:
        n_clean = name.strip()
        n_low = n_clean.lower()
        if not n_clean or len(n_clean) < 2:
            return False
        if any(cat.lower() == n_low for cat in catalog_names):
            return True
        german_stopwords = {
            'in', 'an', 'auf', 'aus', 'bei', 'mit', 'nach', 'seit', 'von', 'zu', 'über', 'unter', 'vor', 'zwischen',
            'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen', 'einem', 'einer', 'eines',
            'wie', 'was', 'wo', 'wann', 'warum', 'wieso', 'weshalb', 'wer', 'wen', 'wem', 'wessen', 'welche', 'welcher', 'welches', 'welchen',
            'ist', 'sind', 'war', 'waren', 'wird', 'werden', 'hat', 'haben', 'hatte', 'hatten',
            'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'meiner', 'meinem', 'meinen', 'meine', 'unserer', 'unserem', 'unsere',
            'noch', 'schon', 'nicht', 'kein', 'keine', 'keinen', 'viel', 'viele', 'alles', 'nichts', 'etwas',
            'grad', 'minuten', 'sekunden', 'stunden', 'uhr', 'timer', 'wecker', 'danke', 'bitte', 'ja', 'nein', 'nee', 'mal', 'eben', 'lang', 'brauchen'
        }
        if n_low in german_stopwords:
            return False
        return True

    def resolve_icon_and_section(self, item_name: str, catalog_sections: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
        """Resolve the most suitable Bring! catalog icon and category section for an item."""
        if not item_name:
            return None, None

        if catalog_sections is None:
            catalog_sections = {}

        low = item_name.lower().strip()

        fallback_sections = {
            'kekse': 'Snacks & Süsswaren', 'schokolade': 'Snacks & Süsswaren',
            'chips': 'Snacks & Süsswaren', 'pommes chips': 'Snacks & Süsswaren',
            'waffeln': 'Snacks & Süsswaren', 'gummibärchen': 'Snacks & Süsswaren',
            'pralinen': 'Snacks & Süsswaren', 'bonbons': 'Snacks & Süsswaren',
            'bier': 'Getränke', 'wein': 'Getränke', 'cola': 'Getränke',
            'limonade': 'Getränke', 'saft': 'Getränke', 'wasser': 'Getränke',
            'mineralwasser': 'Getränke', 'eistee': 'Getränke', 'kaffee': 'Getränke', 'tee': 'Getränke',
            'milch': 'Milch & Käse', 'käse': 'Milch & Käse', 'butter': 'Milch & Käse',
            'joghurt': 'Milch & Käse', 'quark': 'Milch & Käse', 'sahne': 'Milch & Käse',
            'fleisch': 'Fleisch & Fisch', 'wurst': 'Fleisch & Fisch', 'fisch': 'Fleisch & Fisch',
            'schinken': 'Fleisch & Fisch', 'hackfleisch': 'Fleisch & Fisch',
            'brot': 'Brot & Gebäck', 'brötchen': 'Brot & Gebäck', 'toast': 'Brot & Gebäck',
            'pizza': 'Fertig- & Tiefkühlprodukte', 'pommes': 'Fertig- & Tiefkühlprodukte',
            'nudeln': 'Getreideprodukte', 'reis': 'Getreideprodukte', 'spaghetti': 'Getreideprodukte',
            'mehl': 'Zutaten & Gewürze', 'öl': 'Zutaten & Gewürze', 'essig': 'Zutaten & Gewürze',
            'gewürze': 'Zutaten & Gewürze', 'kräuter': 'Obst & Gemüse', 'salat': 'Obst & Gemüse',
            'obst': 'Obst & Gemüse', 'gemüse': 'Obst & Gemüse', 'tomaten': 'Obst & Gemüse',
            'waschmittel': 'Haushalt', 'spülmittel': 'Haushalt', 'toilettenpapier': 'Haushalt',
            'taschentücher': 'Pflege & Gesundheit', 'zahnpasta': 'Pflege & Gesundheit', 'shampoo': 'Pflege & Gesundheit',
        }

        def _get_sec(icon_id: str) -> str:
            if not icon_id:
                return ''
            i_low = icon_id.lower()
            if i_low in catalog_sections:
                val = catalog_sections[i_low]
                return val[1] if isinstance(val, (list, tuple)) else str(val)
            return fallback_sections.get(i_low, '')

        # 1. Exact match in catalog sections
        if low in catalog_sections:
            val = catalog_sections[low]
            icon = val[0] if isinstance(val, (list, tuple)) else item_name
            sec = val[1] if isinstance(val, (list, tuple)) else str(val)
            return icon, sec

        # 2. Canonical synonyms
        if low in self.bring_canonical_synonyms:
            canon_name, _ = self.bring_canonical_synonyms[low]
            return canon_name, _get_sec(canon_name)

        # 3. Unambiguous brand categories
        if low in self.unambiguous_brand_categories:
            cat_icon, _ = self.unambiguous_brand_categories[low]
            return cat_icon, _get_sec(cat_icon)

        # 4. Compound suffix match (e.g. Nutellakekse -> Kekse, Dosenwurst -> Wurst)
        for suffix, target_cat in sorted(self.cat_head_nouns.items(), key=lambda x: len(x[0]), reverse=True):
            if low.endswith(suffix) and len(low) > len(suffix) + 1:
                return target_cat, _get_sec(target_cat)

        # 5. Grain style match (e.g. Vollkorntoast -> Toast)
        for prefix in self.grain_style_prefixes:
            if low.startswith(prefix) and len(low) > len(prefix) + 2:
                rest = low[len(prefix):].strip()
                if rest in self.cat_head_nouns:
                    icon = self.cat_head_nouns[rest]
                    return icon, _get_sec(icon)
                if rest in catalog_sections:
                    val = catalog_sections[rest]
                    icon = val[0] if isinstance(val, (list, tuple)) else rest.capitalize()
                    return icon, _get_sec(icon)

        # 6. Word boundary match (e.g. Gustavo Gusto Pizza -> Pizza, Italienische Kräuter -> Kräuter)
        words = low.split()
        for w in words:
            if w in self.unambiguous_brand_categories:
                cat_icon, _ = self.unambiguous_brand_categories[w]
                return cat_icon, _get_sec(cat_icon)
            if w in self.cat_head_nouns:
                icon = self.cat_head_nouns[w]
                return icon, _get_sec(icon)
            if w in catalog_sections:
                val = catalog_sections[w]
                icon = val[0] if isinstance(val, (list, tuple)) else w.capitalize()
                return icon, _get_sec(icon)

        return None, None

    def parse_items(self, raw_text: str, catalog_names: list[str]) -> list[dict[str, str]]:
        if not raw_text or not isinstance(raw_text, str):
            return []

        norm = self.normalize_spoken_german(raw_text)
        cleaned = self.strip_command_phrases(norm)
        if not cleaned:
            return []

        common_stt_typos = {
            'bankmischung': 'backmischung',
            'backwäsche': 'backmischung',
            'backwaesche': 'backmischung',
            'küche': 'kiste',
            'bunt': 'bund'
        }
        for typo, repl in common_stt_typos.items():
            cleaned = re.sub(rf'\b{typo}\b', repl, cleaned, flags=re.IGNORECASE)

        cleaned_low = cleaned.lower()
        for cat in catalog_names:
            clow = cat.lower()
            if clow == cleaned_low or clow.replace(" ", "") == cleaned_low.replace(" ", ""):
                return [{'name': cat, 'specification': ''}]

        first_split = re.split(r'\s+(?:und|sowie|\+)\s+|,\s*', cleaned, flags=re.IGNORECASE)

        split_pattern = rf'(?<=[a-zA-ZäöüÄÖÜß])\s+(?=\d+(?:[.,]\d+)?\s+(?:(?:{self.units_pattern})\s+)[a-zA-ZäöüÄÖÜß]+|\d+(?:[.,]\d+)?\s+(?!(?:{self.units_pattern})\b)[a-zA-ZäöüÄÖÜß]+)'
        split_regex_smart = re.compile(split_pattern, re.IGNORECASE)

        chunks = []
        for fs in first_split:
            fs = fs.strip()
            if not fs:
                continue
            splits = split_regex_smart.split(fs)
            chunks.extend([s.strip() for s in splits if s.strip()])

        items = []
        for chunk in chunks:
            sub_items = self.smart_split_consecutive(chunk, catalog_names)
            for sub in sub_items:
                name, spec = self.extract_specification(sub)
                if not name:
                    continue
                low_name = name.lower().strip()

                # 1. Grain style prefix + grain noun (e.g. Vollkorntoast, Toast Vollkorn)
                matched_grain = False
                for gp in self.grain_style_prefixes:
                    if low_name.startswith(gp):
                        rest = low_name[len(gp):].strip()
                        if rest in self.known_grain_nouns:
                            name = rest.capitalize()
                            spec = f"{spec} {gp.capitalize()}".strip() if spec else gp.capitalize()
                            matched_grain = True
                            break
                    elif low_name.endswith(gp):
                        base = low_name[:-len(gp)].strip()
                        if base in self.known_grain_nouns:
                            name = base.capitalize()
                            spec = f"{spec} {gp.capitalize()}".strip() if spec else gp.capitalize()
                            matched_grain = True
                            break

                # 2. Multi-word brand + catalog noun (e.g. Gustavo Gusto Pizza, Pizza Gustavo Gusto)
                if not matched_grain:
                    for b in sorted(self.brand_map.keys(), key=len, reverse=True):
                        b_disp = self.brand_map[b]
                        if low_name.startswith(b + ' '):
                            noun = low_name[len(b)+1:].strip()
                            if noun in [c.lower() for c in catalog_names]:
                                name = noun.capitalize()
                                spec = f"{spec} {b_disp}".strip() if spec else b_disp
                                break
                        elif low_name.endswith(' ' + b):
                            noun = low_name[:-len(b)-1].strip()
                            if noun in [c.lower() for c in catalog_names]:
                                name = noun.capitalize()
                                spec = f"{spec} {b_disp}".strip() if spec else b_disp
                                break

                low_name = name.lower().strip()
                if low_name in self.bring_canonical_synonyms:
                    canon_name, canon_spec = self.bring_canonical_synonyms[low_name]
                    final_name = canon_name
                    final_spec = f"{spec} {canon_spec}".strip() if spec else canon_spec
                else:
                    final_name = self.match_catalog_name(name, catalog_names)
                    final_spec = spec
                if self.is_valid_grocery_item(final_name, catalog_names):
                    items.append({'name': final_name, 'specification': final_spec})

        deduped = {}
        for item in items:
            name = item['name']
            spec = item.get('specification', '').strip()
            if name not in deduped:
                deduped[name] = spec
            else:
                existing_spec = deduped[name]
                if not existing_spec and spec:
                    deduped[name] = spec
                elif existing_spec and spec and spec.lower() not in existing_spec.lower():
                    deduped[name] = f"{existing_spec} {spec}".strip()

        return [{'name': k, 'specification': v} for k, v in deduped.items()]

def detect_operation(raw_text: str) -> str:
    """Detect if items should be added or removed."""
    low = raw_text.lower()
    delete_words = [
        'lösch', 'lösche', 'entfern', 'entferne', 'streich', 'streiche',
        'nimm', 'runter', 'weg', 'löschen', 'entfernen', 'streichen',
        'abhak', 'abgehakt', 'erledigt', 'gekauft'
    ]
    for w in delete_words:
        if w in low:
            return 'TO_RECENTLY'
    if ('hak' in low or 'hake' in low) and ('ab' in low or 'weg' in low):
        return 'TO_RECENTLY'
    return 'TO_PURCHASE'
