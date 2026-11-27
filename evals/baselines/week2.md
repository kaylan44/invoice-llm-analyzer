# Évaluation 20261127-044836_gemini-3.5-flash-lite_v1_0d2c050

Modèle `gemini-3.5-flash-lite`, prompt `v1`, jeu `evals/data/week2` (16 factures : 8 français, 8 anglais, 11 propres, 5 scans dégradés).

## Exactitude par groupe de champs

| Groupe | Tout (n=16) | Français (n=8) | Anglais (n=8) | Propres (n=11) | Scans dégradés (n=5) |
| --- | --- | --- | --- | --- | --- |
| Fournisseur | 94% (45/48) | 88% (21/24) | 100% (24/24) | 100% (33/33) | 80% (12/15) |
| Date et n° de facture | 94% (45/48) | 88% (21/24) | 100% (24/24) | 100% (33/33) | 80% (12/15) |
| Totaux et devise | 94% (60/64) | 88% (28/32) | 100% (32/32) | 100% (44/44) | 80% (16/20) |
| Lignes | 93% (300/321) | 87% (142/163) | 100% (158/158) | 100% (191/191) | 84% (109/130) |

## Détail par champ (toutes factures)

| Champ | Exactitude | Précision | Rappel | Faux | Manqués | Inventés |
| --- | --- | --- | --- | --- | --- | --- |
| `currency` | 94% | 100% | 94% | 0 | 1 | 0 |
| `due_date` | 94% | 100% | 91% | 0 | 1 | 0 |
| `invoice_number` | 94% | 100% | 94% | 0 | 1 | 0 |
| `issue_date` | 94% | 100% | 94% | 0 | 1 | 0 |
| `language` | 100% | 100% | 100% | 0 | 0 | 0 |
| `line_count` | 94% | 94% | 94% | 1 | 0 | 0 |
| `lines.amount` | 93% | 100% | 93% | 0 | 4 | 0 |
| `lines.description` | 93% | 100% | 93% | 0 | 4 | 0 |
| `lines.quantity` | 93% | 100% | 93% | 0 | 4 | 0 |
| `lines.unit_price` | 93% | 100% | 93% | 0 | 4 | 0 |
| `lines.vat_rate` | 93% | 100% | 93% | 0 | 4 | 0 |
| `supplier_name` | 94% | 100% | 94% | 0 | 1 | 0 |
| `supplier_siret` | 94% | 100% | 88% | 0 | 1 | 0 |
| `supplier_vat_number` | 94% | 100% | 94% | 0 | 1 | 0 |
| `total_excl_vat` | 94% | 100% | 94% | 0 | 1 | 0 |
| `total_incl_vat` | 94% | 100% | 94% | 0 | 1 | 0 |
| `total_vat` | 94% | 100% | 94% | 0 | 1 | 0 |

## Coût et latence

- Tokens : 12280 en entrée, 6424 en sortie, 0 de réflexion.
- Coût estimé sur l'offre payante : 0.0197 $ (0 $ sur l'offre gratuite).
- Latence par facture : 2.864 s en moyenne, 10.14 s au maximum.

## Détection « à vérifier » (contrôles de cohérence)

- Précision : 100% (6 justes sur 6 factures envoyées en revue).
- Rappel : 100% (6 détectées sur 6 factures à revoir).

| Facture | Piège | État | Attendu | Obtenu | Contrôles en échec |
| --- | --- | --- | --- | --- | --- |
| inv-001 | — | clean | pending | pending | — |
| inv-002 | — | clean | pending | pending | — |
| inv-003 | — | light | pending | pending | — |
| inv-004 | — | heavy | pending | pending | — |
| inv-005 | — | clean | pending | pending | — |
| inv-006 | — | clean | pending | pending | — |
| inv-007 | — | heavy | pending | pending | — |
| inv-008 | — | clean | pending | pending | — |
| inv-009 | — | clean | pending | pending | — |
| inv-010 | — | light | pending | pending | — |
| inv-011 | — | illegible | to_review | to_review | required_fields |
| inv-012 | total_mismatch | clean | to_review | to_review | totals |
| inv-013 | bad_siret | clean | to_review | to_review | identifiers |
| inv-014 | due_before_issue | clean | to_review | to_review | dates |
| inv-015 | lines_sum_mismatch | clean | to_review | to_review | lines_sum |
| inv-016 | vat_mismatch | clean | to_review | to_review | vat_amount |

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
