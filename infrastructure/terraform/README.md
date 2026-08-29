# Infrastructure (Terraform)

Placeholder — provisioned in **Phase 4** (`CLAUDE.md` §15).

Planned modules (`CLAUDE.md` §5): `networking`, `ecs` (API + worker services),
`elasticache`, `alb` (HTTPS, SSE idle timeout 300s), `sqs` (+ DLQs), `s3`
(+ CloudFront). Secrets via AWS Secrets Manager. CI/CD via GitHub Actions
(test → build → ECR → ECS rolling deploy).
