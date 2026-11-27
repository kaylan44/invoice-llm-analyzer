# Évaluation 20261127-073716_gemini-3.5-flash-lite_agent-v1_389febd-dirty

Modèle `gemini-3.5-flash-lite`, prompt `agent-v1`, jeu `evals/data/week2` (16 factures : 8 français, 8 anglais, 11 propres, 5 scans dégradés).

## Exactitude par groupe de champs

| Groupe | Tout (n=16) | Français (n=8) | Anglais (n=8) | Propres (n=11) | Scans dégradés (n=5) |
| --- | --- | --- | --- | --- | --- |
| Fournisseur | 96% (46/48) | 96% (23/24) | 96% (23/24) | 97% (32/33) | 93% (14/15) |
| Date et n° de facture | 100% (48/48) | 100% (24/24) | 100% (24/24) | 100% (33/33) | 100% (15/15) |
| Totaux et devise | 95% (61/64) | 91% (29/32) | 100% (32/32) | 100% (44/44) | 85% (17/20) |
| Lignes | 100% (321/321) | 100% (163/163) | 100% (158/158) | 100% (191/191) | 100% (130/130) |

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
| `supplier_name` | 94% | 94% | 94% | 1 | 0 | 0 |
| `supplier_siret` | 100% | 100% | 100% | 0 | 0 | 0 |
| `supplier_vat_number` | 94% | 94% | 94% | 1 | 0 | 0 |
| `total_excl_vat` | 94% | 94% | 100% | 0 | 0 | 1 |
| `total_incl_vat` | 94% | 94% | 100% | 0 | 0 | 1 |
| `total_vat` | 94% | 94% | 100% | 0 | 0 | 1 |

## Coût et latence

- Tokens : 69786 en entrée, 9446 en sortie, 0 de réflexion.
- Coût estimé sur l'offre payante : 0.0445 $ (0 $ sur l'offre gratuite).
- Latence par facture : 6.337 s en moyenne, 20.202 s au maximum.

## Détection « à vérifier » (contrôles de cohérence)

- Précision : 83% (5 justes sur 6 factures envoyées en revue).
- Rappel : 83% (5 détectées sur 6 factures à revoir).

| Facture | Piège | État | Attendu | Obtenu | Contrôles en échec |
| --- | --- | --- | --- | --- | --- |
| inv-001 | — | clean | pending | pending | — |
| inv-002 | — | clean | pending | pending | — |
| inv-003 | — | light | pending | pending | — |
| inv-004 | — | heavy | pending | pending | — |
| inv-005 | — | clean | pending | pending | — |
| inv-006 | — | clean | pending | pending | — |
| inv-007 | — | heavy | pending | to_review ✗ | identifiers |
| inv-008 | — | clean | pending | pending | — |
| inv-009 | — | clean | pending | pending | — |
| inv-010 | — | light | pending | pending | — |
| inv-011 | — | stain | to_review | pending ✗ | — |
| inv-012 | total_mismatch | clean | to_review | to_review | totals |
| inv-013 | bad_siret | clean | to_review | to_review | identifiers |
| inv-014 | due_before_issue | clean | to_review | to_review | dates |
| inv-015 | lines_sum_mismatch | clean | to_review | to_review | lines_sum |
| inv-016 | vat_mismatch | clean | to_review | to_review | vat_amount |

## Échecs d'extraction

Aucun.

## Champs masqués par une tache

La bonne réponse est `null` : la valeur n'est pas lisible. Une valeur donnée veut dire que le modèle l'a devinée ou recalculée, ce que le prompt interdit.

| Facture | Champ | Imprimé (sous la tache) | Obtenu | Comportement |
| --- | --- | --- | --- | --- |
| inv-011 | `total_excl_vat` | '509' | '509' | valeur donnée ✗ |
| inv-011 | `total_vat` | '101.8' | '101.8' | valeur donnée ✗ |
| inv-011 | `total_incl_vat` | '610.8' | '610.8' | valeur donnée ✗ |

## Analyse des erreurs (chaque champ faux, manqué ou inventé)

Les champs marqués « masqué » étaient sous une tache : `null` y est la bonne réponse, une valeur y est comptée « inventée ».

| Facture | Segment | Champ | Résultat | Attendu | Obtenu |
| --- | --- | --- | --- | --- | --- |
| inv-007 | fr, heavy | `supplier_vat_number` | wrong | 'FR55139117188' | 'FR5539117188' |
| inv-011 | fr, stain | `total_excl_vat` | hallucinated (masqué) | '509' | '509' |
| inv-011 | fr, stain | `total_vat` | hallucinated (masqué) | '101.8' | '101.8' |
| inv-011 | fr, stain | `total_incl_vat` | hallucinated (masqué) | '610.8' | '610.8' |
| inv-012 | en, clean | `supplier_name` | wrong | 'lewis watson and singh' | 'lewiswatson and singh' |
