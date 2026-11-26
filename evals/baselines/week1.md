# Évaluation 20261126-110514_gemini-3.5-flash-lite_v1_573c76f

Modèle `gemini-3.5-flash-lite`, prompt `v1`, jeu `evals/data/week1` (11 factures : 6 français, 5 anglais, 6 propres, 5 scans dégradés).

## Exactitude par groupe de champs

| Groupe | Tout (n=11) | Français (n=6) | Anglais (n=5) | Propres (n=6) | Scans dégradés (n=5) |
| --- | --- | --- | --- | --- | --- |
| Fournisseur | 91% (30/33) | 83% (15/18) | 100% (15/15) | 100% (18/18) | 80% (12/15) |
| Date et n° de facture | 91% (30/33) | 83% (15/18) | 100% (15/15) | 100% (18/18) | 80% (12/15) |
| Totaux et devise | 91% (40/44) | 83% (20/24) | 100% (20/20) | 100% (24/24) | 80% (16/20) |
| Lignes | 92% (230/251) | 84% (110/131) | 100% (120/120) | 100% (121/121) | 84% (109/130) |

## Détail par champ (toutes factures)

| Champ | Exactitude | Précision | Rappel | Faux | Manqués | Inventés |
| --- | --- | --- | --- | --- | --- | --- |
| `currency` | 91% | 100% | 91% | 0 | 1 | 0 |
| `due_date` | 91% | 100% | 86% | 0 | 1 | 0 |
| `invoice_number` | 91% | 100% | 91% | 0 | 1 | 0 |
| `issue_date` | 91% | 100% | 91% | 0 | 1 | 0 |
| `language` | 100% | 100% | 100% | 0 | 0 | 0 |
| `line_count` | 91% | 91% | 91% | 1 | 0 | 0 |
| `lines.amount` | 92% | 100% | 92% | 0 | 4 | 0 |
| `lines.description` | 92% | 100% | 92% | 0 | 4 | 0 |
| `lines.quantity` | 92% | 100% | 92% | 0 | 4 | 0 |
| `lines.unit_price` | 92% | 100% | 92% | 0 | 4 | 0 |
| `lines.vat_rate` | 92% | 100% | 92% | 0 | 4 | 0 |
| `supplier_name` | 91% | 100% | 91% | 0 | 1 | 0 |
| `supplier_siret` | 91% | 100% | 83% | 0 | 1 | 0 |
| `supplier_vat_number` | 91% | 100% | 91% | 0 | 1 | 0 |
| `total_excl_vat` | 91% | 100% | 91% | 0 | 1 | 0 |
| `total_incl_vat` | 91% | 100% | 91% | 0 | 1 | 0 |
| `total_vat` | 91% | 100% | 91% | 0 | 1 | 0 |

## Coût et latence

- Tokens : 8455 en entrée, 4649 en sortie, 0 de réflexion.
- Coût estimé sur l'offre payante : 0.0142 $ (0 $ sur l'offre gratuite).
- Latence par facture : 5.486 s en moyenne, 12.955 s au maximum.

## Échecs d'extraction

Aucun.

## Analyse des erreurs (chaque champ faux, manqué ou inventé)

| Facture | Segment | Champ | Résultat | Attendu | Obtenu |
| --- | --- | --- | --- | --- | --- |
| inv-011 | fr, illegible | `supplier_name` | missed | 'bonnin' | None |
| inv-011 | fr, illegible | `supplier_vat_number` | missed | 'FR71787234301' | None |
| inv-011 | fr, illegible | `supplier_siret` | missed | '78723430198055' | None |
| inv-011 | fr, illegible | `invoice_number` | missed | 'FAC-2026-0937' | None |
| inv-011 | fr, illegible | `issue_date` | missed | '2026-09-04' | None |
| inv-011 | fr, illegible | `due_date` | missed | '2026-10-19' | None |
| inv-011 | fr, illegible | `currency` | missed | 'EUR' | None |
| inv-011 | fr, illegible | `total_excl_vat` | missed | '509' | None |
| inv-011 | fr, illegible | `total_vat` | missed | '101.8' | None |
| inv-011 | fr, illegible | `total_incl_vat` | missed | '610.8' | None |
| inv-011 | fr, illegible | `line_count` | wrong | '4' | '0' |
| inv-011 | fr, illegible | `lines.description (ligne 1)` | missed | 'ramettes papier a4 80 g' | None |
| inv-011 | fr, illegible | `lines.quantity (ligne 1)` | missed | '5' | None |
| inv-011 | fr, illegible | `lines.unit_price (ligne 1)` | missed | '4.9' | None |
| inv-011 | fr, illegible | `lines.vat_rate (ligne 1)` | missed | '20' | None |
| inv-011 | fr, illegible | `lines.amount (ligne 1)` | missed | '24.5' | None |
| inv-011 | fr, illegible | `lines.description (ligne 2)` | missed | 'cartouches toner noir' | None |
| inv-011 | fr, illegible | `lines.quantity (ligne 2)` | missed | '3' | None |
| inv-011 | fr, illegible | `lines.unit_price (ligne 2)` | missed | '62.5' | None |
| inv-011 | fr, illegible | `lines.vat_rate (ligne 2)` | missed | '20' | None |
| inv-011 | fr, illegible | `lines.amount (ligne 2)` | missed | '187.5' | None |
| inv-011 | fr, illegible | `lines.description (ligne 3)` | missed | 'maintenance informatique' | None |
| inv-011 | fr, illegible | `lines.quantity (ligne 3)` | missed | '2' | None |
| inv-011 | fr, illegible | `lines.unit_price (ligne 3)` | missed | '75' | None |
| inv-011 | fr, illegible | `lines.vat_rate (ligne 3)` | missed | '20' | None |
| inv-011 | fr, illegible | `lines.amount (ligne 3)` | missed | '150' | None |
| inv-011 | fr, illegible | `lines.description (ligne 4)` | missed | 'abonnement logiciel mensuel' | None |
| inv-011 | fr, illegible | `lines.quantity (ligne 4)` | missed | '3' | None |
| inv-011 | fr, illegible | `lines.unit_price (ligne 4)` | missed | '49' | None |
| inv-011 | fr, illegible | `lines.vat_rate (ligne 4)` | missed | '20' | None |
| inv-011 | fr, illegible | `lines.amount (ligne 4)` | missed | '147' | None |
