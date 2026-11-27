# Évaluation 20261127-073443_gemini-3.5-flash-lite_agent-v1_389febd-dirty

Modèle `gemini-3.5-flash-lite`, prompt `agent-v1`, jeu `evals/data/week3` (24 factures : 12 français, 12 anglais, 12 propres, 12 scans dégradés, 8 multipages, 12 pièges de lecture).

## Exactitude par groupe de champs

| Groupe | Tout (n=24) | Français (n=12) | Anglais (n=12) | Propres (n=12) | Scans dégradés (n=12) | Multipages (n=8) | Pièges de lecture (n=12) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Fournisseur | 99% (71/72) | 97% (35/36) | 100% (36/36) | 100% (36/36) | 97% (35/36) | 100% (24/24) | 100% (36/36) |
| Date et n° de facture | 99% (71/72) | 100% (36/36) | 97% (35/36) | 100% (36/36) | 97% (35/36) | 96% (23/24) | 100% (36/36) |
| Totaux et devise | 100% (96/96) | 100% (48/48) | 100% (48/48) | 100% (48/48) | 100% (48/48) | 100% (32/32) | 100% (48/48) |
| Lignes | 99% (1860/1874) | 99% (890/897) | 99% (970/977) | 100% (947/947) | 98% (913/927) | 99% (1604/1618) | 100% (597/597) |

## Détail par champ (toutes factures)

| Champ | Exactitude | Précision | Rappel | Faux | Manqués | Inventés |
| --- | --- | --- | --- | --- | --- | --- |
| `currency` | 100% | 100% | 100% | 0 | 0 | 0 |
| `due_date` | 96% | 95% | 100% | 0 | 0 | 1 |
| `invoice_number` | 100% | 100% | 100% | 0 | 0 | 0 |
| `issue_date` | 100% | 100% | 100% | 0 | 0 | 0 |
| `language` | 100% | 100% | 100% | 0 | 0 | 0 |
| `line_count` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.amount` | 99% | 99% | 99% | 3 | 0 | 0 |
| `lines.description` | 98% | 98% | 98% | 8 | 0 | 0 |
| `lines.quantity` | 99% | 99% | 99% | 3 | 0 | 0 |
| `lines.unit_price` | 100% | 100% | 100% | 0 | 0 | 0 |
| `lines.vat_rate` | 100% | 100% | 100% | 0 | 0 | 0 |
| `supplier_name` | 100% | 100% | 100% | 0 | 0 | 0 |
| `supplier_siret` | 96% | 92% | 92% | 1 | 0 | 0 |
| `supplier_vat_number` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_excl_vat` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_incl_vat` | 100% | 100% | 100% | 0 | 0 | 0 |
| `total_vat` | 100% | 100% | 100% | 0 | 0 | 0 |

## Coût et latence

- Tokens : 125377 en entrée, 39780 en sortie, 0 de réflexion.
- Coût estimé sur l'offre payante : 0.1371 $ (0 $ sur l'offre gratuite).
- Latence par facture : 5.73 s en moyenne, 10.571 s au maximum.

## Détection « à vérifier » (contrôles de cohérence)

- Précision : 0% (0 justes sur 2 factures envoyées en revue).
- Rappel : — (0 détectées sur 0 factures à revoir).

| Facture | Piège | État | Attendu | Obtenu | Contrôles en échec |
| --- | --- | --- | --- | --- | --- |
| inv-001 | — | clean | pending | pending | — |
| inv-002 | — | clean | pending | pending | — |
| inv-003 | — | clean | pending | pending | — |
| inv-004 | — | clean | pending | pending | — |
| inv-005 | — | medium | pending | to_review ✗ | lines_sum, vat_amount |
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
| inv-005 | fr, medium, long | `lines.quantity (ligne 19)` | wrong | '3' | '2' |
| inv-005 | fr, medium, long | `lines.amount (ligne 19)` | wrong | '55.5' | '37' |
| inv-005 | fr, medium, long | `lines.quantity (ligne 21)` | wrong | '1' | '10' |
| inv-005 | fr, medium, long | `lines.amount (ligne 21)` | wrong | '4.9' | '49' |
| inv-005 | fr, medium, long | `lines.quantity (ligne 22)` | wrong | '10' | '1' |
| inv-005 | fr, medium, long | `lines.amount (ligne 22)` | wrong | '49' | '4.9' |
| inv-005 | fr, medium, long | `lines.description (ligne 39)` | wrong | 'cartouches toner noir ref b8999' | 'cartouches toner noir ref b9999' |
| inv-006 | en, medium, long | `lines.description (ligne 2)` | wrong | 'courier delivery ref c2616' | 'courier delivery ref c2614' |
| inv-006 | en, medium, long | `lines.description (ligne 13)` | wrong | 'courier delivery ref b9080' | 'courier delivery ref 89080' |
| inv-006 | en, medium, long | `lines.description (ligne 19)` | wrong | 'a4 copier paper box of 5 reams ref c5853' | 'a4 copier paper box of 5 reams ref c3853' |
| inv-006 | en, medium, long | `lines.description (ligne 20)` | wrong | 'monthly software subscription ref a7883' | 'monthly software subscription ref a7683' |
| inv-006 | en, medium, long | `lines.description (ligne 24)` | wrong | 'child car seat ref b3321' | 'child car seat ref 83321' |
| inv-006 | en, medium, long | `lines.description (ligne 25)` | wrong | 'child car seat ref e0126' | 'child car seat ref 80126' |
| inv-006 | en, medium, long | `lines.description (ligne 40)` | wrong | 'child car seat ref k8468' | 'child car seat ref kb468' |
| inv-008 | en, light, long | `due_date` | hallucinated | None | '2026-07-05' |
| inv-017 | fr, medium | `supplier_siret` | wrong | '94585003070387' | '94585003076387' |
