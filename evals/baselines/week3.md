# Évaluation 20261127-071959_gemini-3.5-flash-lite_v1_9a4ba65-dirty

Modèle `gemini-3.5-flash-lite`, prompt `v1`, jeu `evals/data/week3` (24 factures : 12 français, 12 anglais, 12 propres, 12 scans dégradés, 8 multipages, 12 pièges de lecture).

## Exactitude par groupe de champs

| Groupe | Tout (n=24) | Français (n=12) | Anglais (n=12) | Propres (n=12) | Scans dégradés (n=12) | Multipages (n=8) | Pièges de lecture (n=12) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Fournisseur | 99% (71/72) | 97% (35/36) | 100% (36/36) | 100% (36/36) | 97% (35/36) | 100% (24/24) | 100% (36/36) |
| Date et n° de facture | 100% (72/72) | 100% (36/36) | 100% (36/36) | 100% (36/36) | 100% (36/36) | 100% (24/24) | 100% (36/36) |
| Totaux et devise | 100% (96/96) | 100% (48/48) | 100% (48/48) | 100% (48/48) | 100% (48/48) | 100% (32/32) | 100% (48/48) |
| Lignes | 100% (1865/1874) | 100% (895/897) | 99% (970/977) | 100% (947/947) | 99% (918/927) | 99% (1609/1618) | 100% (597/597) |

## Détail par champ (toutes factures)

| Champ | Exactitude | Précision | Rappel | Faux | Manqués | Inventés |
| --- | --- | --- | --- | --- | --- | --- |
| `currency` | 100% | 100% | 100% | 0 | 0 | 0 |
| `due_date` | 100% | 100% | 100% | 0 | 0 | 0 |
| `invoice_number` | 100% | 100% | 100% | 0 | 0 | 0 |
| `issue_date` | 100% | 100% | 100% | 0 | 0 | 0 |
| `language` | 100% | 100% | 100% | 0 | 0 | 0 |
| `line_count` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.amount` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.description` | 98% | 98% | 98% | 9 | 0 | 0 |
| `lines.quantity` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.unit_price` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.vat_rate` | 100% | 100% | 100% | 0 | 0 | 0 |
| `supplier_name` | 100% | 100% | 100% | 0 | 0 | 0 |
| `supplier_siret` | 96% | 92% | 92% | 1 | 0 | 0 |
| `supplier_vat_number` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_excl_vat` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_incl_vat` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_vat` | 100% | 100% | 100% | 0 | 0 | 0 |

## Coût et latence

- Tokens : 22720 en entrée, 30252 en sortie, 0 de réflexion.
- Coût estimé sur l'offre payante : 0.0824 $ (0 $ sur l'offre gratuite).
- Latence par facture : 3.658 s en moyenne, 7.366 s au maximum.

## Détection « à vérifier » (contrôles de cohérence)

- Précision : 0% (0 justes sur 1 factures envoyées en revue).
- Rappel : — (0 détectées sur 0 factures à revoir).

| Facture | Piège | État | Attendu | Obtenu | Contrôles en échec |
| --- | --- | --- | --- | --- | --- |
| inv-001 | — | clean | pending | pending | — |
| inv-002 | — | clean | pending | pending | — |
| inv-003 | — | clean | pending | pending | — |
| inv-004 | — | clean | pending | pending | — |
| inv-005 | — | medium | pending | pending | — |
| inv-006 | — | medium | pending | pending | — |
| inv-007 | — | light | pending | pending | — |
| inv-008 | — | light | pending | pending | — |
| inv-009 | — | clean | pending | pending | — |
| inv-010 | — | clean | pending | pending | — |
| inv-011 | — | clean | pending | pending | — |
| inv-012 | — | clean | pending | pending | — |
| inv-013 | — | clean | pending | pending | — |
| inv-014 | — | clean | pending | pending | — |
| inv-015 | — | medium | pending | pending | — |
| inv-016 | — | medium | pending | pending | — |
| inv-017 | — | medium | pending | to_review ✗ | identifiers |
| inv-018 | — | medium | pending | pending | — |
| inv-019 | — | heavy | pending | pending | — |
| inv-020 | — | heavy | pending | pending | — |
| inv-021 | — | clean | pending | pending | — |
| inv-022 | — | clean | pending | pending | — |
| inv-023 | — | light | pending | pending | — |
| inv-024 | — | light | pending | pending | — |

## Échecs d'extraction

Aucun.

## Analyse des erreurs (chaque champ faux, manqué ou inventé)

Les champs marqués « masqué » étaient sous une tache : `null` y est la bonne réponse, une valeur y est comptée « inventée ».

| Facture | Segment | Champ | Résultat | Attendu | Obtenu |
| --- | --- | --- | --- | --- | --- |
| inv-005 | fr, medium, long | `lines.description (ligne 38)` | wrong | 'repas d affaires ref b8300' | 'repas d affaires ref 88300' |
| inv-005 | fr, medium, long | `lines.description (ligne 39)` | wrong | 'cartouches toner noir ref b8999' | 'cartouches toner noir ref 88999' |
| inv-006 | en, medium, long | `lines.description (ligne 4)` | wrong | 'a4 copier paper box of 5 reams ref a0206' | 'a4 copier paper box of 5 reams ref a0208' |
| inv-006 | en, medium, long | `lines.description (ligne 13)` | wrong | 'courier delivery ref b9080' | 'courier delivery ref 89080' |
| inv-006 | en, medium, long | `lines.description (ligne 17)` | wrong | 'a4 copier paper box of 5 reams ref f9168' | 'a4 copier paper box of 5 reams ref f9160' |
| inv-006 | en, medium, long | `lines.description (ligne 19)` | wrong | 'a4 copier paper box of 5 reams ref c5853' | 'a4 copier paper box of 5 reams ref c3853' |
| inv-006 | en, medium, long | `lines.description (ligne 24)` | wrong | 'child car seat ref b3321' | 'child car seat ref 83321' |
| inv-006 | en, medium, long | `lines.description (ligne 25)` | wrong | 'child car seat ref e0126' | 'child car seat ref 80126' |
| inv-006 | en, medium, long | `lines.description (ligne 37)` | wrong | 'lever arch files ref e5551' | 'lever arch files ref e3551' |
| inv-017 | fr, medium | `supplier_siret` | wrong | '94585003070387' | '94585003076387' |
