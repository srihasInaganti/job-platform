# GitHub OIDC Identity Provider (only one per AWS account)
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a3a8518e8759bf075b76b750d4f8d44034c2"]
}
# Trust policy allowing only your GitHub repo's main branch to assume the role
data "aws_iam_policy_document" "github_oidc_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      # REPLACE with your GitHub org/user and repo name:
      values = ["repo:srihasInaganti/job-platform:*"]
    }
  }
}

resource "aws_iam_role" "github_deploy_role" {
  name               = "github-actions-deploy-role"
  assume_role_policy = data.aws_iam_policy_document.github_oidc_assume.json
}

# Grant administrator or scoped deployment permissions for Terraform & ECR
resource "aws_iam_role_policy_attachment" "deploy_admin" {
  role       = aws_iam_role.github_deploy_role.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

output "deploy_role_arn" {
  value = aws_iam_role.github_deploy_role.arn
}