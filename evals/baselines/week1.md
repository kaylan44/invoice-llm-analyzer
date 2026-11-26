# Évaluation 20261126-104720_gemini-3.5-flash-lite_v1_2a1a570

Modèle `gemini-3.5-flash-lite`, prompt `v1`, jeu `evals/data/week1` (10 factures : 5 français, 5 anglais, 6 propres, 4 scans dégradés).

## Exactitude par groupe de champs

| Groupe | Tout (n=10) | Français (n=5) | Anglais (n=5) | Propres (n=6) | Scans dégradés (n=4) |
| --- | --- | --- | --- | --- | --- |
| Fournisseur | 100% (30/30) | 100% (15/15) | 100% (15/15) | 100% (18/18) | 100% (12/12) |
| Date et n° de facture | 100% (30/30) | 100% (15/15) | 100% (15/15) | 100% (18/18) | 100% (12/12) |
| Totaux et devise | 100% (40/40) | 100% (20/20) | 100% (20/20) | 100% (24/24) | 100% (16/16) |
| Lignes | 100% (230/230) | 100% (110/110) | 100% (120/120) | 100% (121/121) | 100% (109/109) |

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
| `lines.description` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.quantity` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.unit_price` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.vat_rate` | 100% | 100% | 100% | 0 | 0 | 0 |
| `supplier_name` | 100% | 100% | 100% | 0 | 0 | 0 |
| `supplier_siret` | 100% | 100% | 100% | 0 | 0 | 0 |
| `supplier_vat_number` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_excl_vat` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_incl_vat` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_vat` | 100% | 100% | 100% | 0 | 0 | 0 |

## Coût et latence

- Tokens : 7682 en entrée, 4578 en sortie, 0 de réflexion.
- Coût estimé sur l'offre payante : 0.0138 $ (0 $ sur l'offre gratuite).
- Latence par facture : 4.473 s en moyenne, 8.265 s au maximum.

## Échecs d'extraction

Aucun.

## Analyse des erreurs (chaque champ faux, manqué ou inventé)

Aucune.
