# Corrections du contre-audit MC-NBFX / MC-NBFSE (23 octobre 2026)

## Objectif et point de depart

Cette revision (version `0.5.3.post2`) reprend le code de
`python-wcfbin-conformite-microsoft-final.zip` et les 14 tests independants
produits dans `audit_independant_wcfbin_2026-10-23.zip`.

Avant les corrections : 158 tests historiques passes, mais **10 echecs sur les
14 tests independants**. Ces dix cas se regroupaient en trois familles :
representation des flottants, structure et noms des records XML, longueurs
`Chars32Text`/`Bytes32Text`.

## Modifications apportees

| Bloc | Comportement maintenant impose | References officielles |
| --- | --- | --- |
| `FloatText` 0x90 | Precision IEEE754 simple prise en compte : representation decimale la plus courte permettant de retrouver **les memes 32 bits**, `E` majuscule et signe d'exposant, `INF`, `-INF`, `NaN`, `-0` | MC-NBFX 2.2.3.9 |
| `DoubleText` 0x92 | Representation decimale la plus courte permettant de retrouver **les memes 64 bits** ; memes conventions lexicales | MC-NBFX 2.2.3.10 |
| Tous les attributs 0x04 a 0x3F | Le champ `Value` doit etre un enregistrement `Text` ; les valeurs Element, Attribute, code reserve ou EndListText autonome sont refusees | MC-NBFX 2.2.2 |
| Noms d'elements/attributs | Refus des noms vides et du nom reserve `xmlns`; validation des prefixes et des noms resolus via les dictionnaires statiques/de session | MC-NBFX 2.2.1, 2.2.2 |
| `Chars32Text` 0x9C, `Bytes32Text` 0xA2 | Longueur **INT32 signee strictement positive** a la lecture comme a l'ecriture | MC-NBFX 2.2.3.15, 2.2.3.18 |
| `UnicodeChars32Text` 0xBA | Corrections d'un **ecart supplementaire** repere pendant la relecture : taille UTF-16 representee par `MultiByteInt31`, pas par un entier fixe quatre octets | MC-NBFX 2.2.3.29 |
| Validation de tests | Les cas independants deviennent des tests permanents ; le runner renvoie un code de sortie non nul en cas d'echec | Controle de regression |

Les restrictions ci-dessus sont verifiees aussi pendant `to_bytes()` afin de
bloquer un objet modifie en memoire apres sa construction.

L'encodage XML **reste en texte par defaut**. La conservation des types du flux
binaire, les dictionnaires statiques/persistants et les options de typage
explicite restent disponibles. La version `8.0` demeure une chaine.

## Validation

Depuis la racine du projet :

```sh
python -m tests.alltests
```

Resultat final : **185 tests executes, 185 reussis**. Details dans
`VALIDATION_RESULTS.txt` et dans les fichiers suivants :

- `tests/test_microsoft_independent.py` : 14 tests de l'audit externe ;
- `tests/test_microsoft_boundaries.py` : 13 tests supplementaires, dont un test
  de 5 000 motifs binaires IEEE754 pseudo-aleatoires reproductibles ;
- `tests/test_conformance.py`, `tests/test_session.py`, `tests/test_robustness.py` :
  tests historiques (avec exemples Microsoft et cycles XML/binaires).

Verifications CLI : conversion XML -> NBFX -> XML, conversion XML -> NBFSE
(avec nouvelle table de session) -> XML ; conservation binaire identique du
fichier `example.bin` du projet. Le cas lexical `<Version>8.0</Version>` reste
identique dans les deux modes.

## Limitations et prudence

- **Ne constitue pas une certification de conformite complete** : les 185
  tests ciblent des exigences importantes, mais ne couvrent pas toutes les
  combinaisons de records, les limites de ressources et tous les contrats WCF.
- **Aucun test effectue contre un serveur Microsoft WCF/.NET reel** dans cet
  environnement : le runtime .NET/PowerShell et un serveur de test accessible
  n'etaient pas disponibles. Avant production, valider des echanges reels dans
  les deux sens et la reutilisation de dictionnaires sur plusieurs messages.
- Le projet reste un **codec de documents**, pas une implementation des couches
  de transport et negotiation WCF (MC-NMF, HTTP/TCP, securite, etc.).
- La representation XML des dates/durees suit les clauses normatives MC-NBFX
  2.2.3.12 et 2.2.3.23, qui divergent de certaines tables d'exemples Microsoft.
- Un arbre de records preserve les types binaires ; exporter uniquement un XML
  ordinaire ne suffit pas a reconstruire les types d'origine.

## References Microsoft

- [FloatText §2.2.3.9](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/548c6211-c543-4969-b862-3698ee1f8b71)
- [DoubleText §2.2.3.10](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/4f10b50e-7152-4c28-8c3a-23cfe34eb6c2)
- [ShortAttribute §2.2.2.1](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/6714ac21-d905-49c1-af0b-6c987e9a7080)
- [ShortElement §2.2.1.1](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/70fd89e4-04cc-4266-bfe0-9b39ce86e134)
- [Chars32Text §2.2.3.15](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/cd54178c-4c05-4015-9c33-4c1af139db79)
- [Bytes32Text §2.2.3.18](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/fcabae71-2662-4cbd-a1c7-07512a15f346)
- [UnicodeChars32Text §2.2.3.29](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/e7e8f863-b593-48dd-8345-f9d23b0af2c8)
- [NBFSE StringTable](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfse/a161304c-1a8a-4f31-beec-b96ebc9b1919)
