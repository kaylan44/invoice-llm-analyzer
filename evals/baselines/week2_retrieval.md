# Évaluation du rapprochement (RAG)

Embeddings `gemini-embedding-2` (768 dimensions). Fournisseurs : 41 requêtes ; catégories : 34 requêtes.

## Fournisseurs

| Méthode | recall@1 | recall@3 | recall@5 | MRR |
| --- | --- | --- | --- | --- |
| full_text | 88% | 90% | 90% | 0.890 |
| semantic | 100% | 100% | 100% | 1.000 |
| hybrid | 100% | 100% | 100% | 1.000 |

## Catégories

| Méthode | recall@1 | recall@3 | recall@5 | MRR |
| --- | --- | --- | --- | --- |
| full_text | 71% | 74% | 74% | 0.719 |
| semantic | 97% | 100% | 100% | 0.985 |
| hybrid | 94% | 100% | 100% | 0.961 |

## Requêtes que l'hybride ne classe pas en premier

| Type | Requête | Variante | Rang | En tête |
| --- | --- | --- | --- | --- |
| category | Stylos bille bleus, boîte de 50 | unseen | 3 | 6251 |
| category | Office chair cushion | unseen | 3 | 6064 |
