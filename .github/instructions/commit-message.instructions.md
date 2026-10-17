# Instrucciones para generar mensajes de commit

Estas instrucciones se aplican únicamente a la generación de mensajes de commit mediante IA.

- Genera solo el mensaje de commit, sin explicaciones adicionales ni bloques de código Markdown.
- Usa Conventional Commits: `<type>(<scope>): <description>`. El scope es opcional y debe corresponder al área realmente modificada.
- Elige el tipo según los cambios reales: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore` o `revert`.
- Escribe el título exclusivamente en inglés, incluida la descripción y el scope. Usa una descripción breve en modo imperativo y sin punto final.
- Si existen cambios incompatibles, usa `!` antes de `:` y explica el cambio incompatible tanto en ES como en EN. No lo marques si no está demostrado por el diff.
- Después del título, deja una línea en blanco y escribe primero la sección `ES:` con una lista de cambios en español; después escribe la sección `EN:` con la lista equivalente en inglés.
- Mantén el mismo orden y significado en las dos listas. Cada punto en español debe tener su equivalente en inglés.
- Describe exclusivamente los cambios reales del diff incluido en el commit. Si hay cambios preparados (staged), usa solo esos cambios; no incluyas otros cambios del árbol de trabajo.
- No inventes funcionalidades, motivos, resultados de pruebas, referencias a incidencias, mejoras ni trabajo futuro. No afirmes que se ejecutaron pruebas sin evidencia.
- El ejemplo siguiente ilustra únicamente el formato: no menciones radar ni precipitaciones salvo que esos cambios estén presentes en el diff.
- Limítate a generar el mensaje para que el usuario lo revise. No ejecutes `git add`, `git commit`, `git push` ni otras acciones automáticas sobre Git.

## Ejemplo de formato

```text
feat(radar): add precipitation tracking

ES:

- Implementa el seguimiento de precipitaciones.
- Calcula la dirección y velocidad de desplazamiento.

EN:

- Implements precipitation tracking.
- Calculates movement direction and speed.
```
