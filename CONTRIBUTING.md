# Contributing to Ledgerline

Thank you for your interest in contributing to Ledgerline! This document provides guidelines for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Maintain professional communication

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/ledgerline.git`
3. Create a feature branch: `git checkout -b feature/your-feature-name`
4. Make your changes
5. Test thoroughly
6. Submit a pull request

## Development Setup

```bash
# Clone the repository
git clone https://github.com/ledgerline/ledgerline.git
cd ledgerline

# Copy environment template
cp .env.example .env
# Edit .env and add your API keys

# Start services
docker-compose up -d

# Run tests
./scripts/run-tests.sh
```

## Project Structure

```
OJONE/
├── backend/
│   ├── services/
│   │   ├── go/           # Go microservices
│   │   └── python/       # Python microservices
│   ├── config/           # Configuration files
│   └── kong/             # Kong Gateway plugins
├── frontend/             # Next.js dashboard
├── tests/                # Test suites
└── docker-compose.yml    # Local development setup
```

## Coding Standards

### Go Services

- Follow [Effective Go](https://golang.org/doc/effective_go.html) guidelines
- Use `gofmt` for formatting
- Write unit tests for all functions
- Add godoc comments for exported functions
- Keep functions small and focused

Example:
```go
// CheckRateLimit verifies if a tenant can make a request
// Returns true if allowed, false if rate limited
func CheckRateLimit(ctx context.Context, tenantID string) (bool, error) {
    // Implementation
}
```

### Python Services

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide
- Use type hints for function signatures
- Write docstrings for all functions and classes
- Use `black` for code formatting
- Maximum line length: 100 characters

Example:
```python
async def process_request(request: DispatchRequest) -> DispatchResponse:
    """
    Process an AI request with full Sync-before-ACK guarantees.
    
    Args:
        request: The dispatch request containing provider and model info
        
    Returns:
        DispatchResponse with correlation_id and status
        
    Raises:
        HTTPException: If rate limit exceeded or provider unavailable
    """
    # Implementation
```

### Frontend (React/Next.js)

- Use functional components with hooks
- Follow [React best practices](https://react.dev/learn)
- Use TypeScript for new components (migration in progress)
- Keep components small and reusable
- Add PropTypes or TypeScript types

Example:
```jsx
export function StatusBadge({ status }) {
  const color = getStatusColor(status);
  return (
    <span className={`badge ${color}`}>
      {status}
    </span>
  );
}
```

## Testing

### Unit Tests

```bash
# Go services
cd backend/services/go/rate-limiter
go test -v ./...

# Python services
cd backend/services/python/dispatcher
pytest -v
```

### Integration Tests

```bash
# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Run integration tests
./scripts/integration-tests.sh
```

### Load Tests

```bash
# Install k6
brew install k6  # macOS

# Run load test
k6 run tests/load/phase1_baseline.js
```

## Pull Request Process

1. **Create an Issue First**: For significant changes, open an issue to discuss your proposal
2. **Branch Naming**: Use descriptive names like `feature/semantic-cache` or `fix/rate-limit-bug`
3. **Commit Messages**: Write clear, descriptive commit messages
   - Use present tense: "Add feature" not "Added feature"
   - Reference issues: "Fix #123: Resolve rate limit race condition"
4. **Tests**: Add tests for new features
5. **Documentation**: Update README and relevant docs
6. **Pull Request Description**: Include:
   - What changed and why
   - Related issue numbers
   - Testing performed
   - Screenshots (for UI changes)

## Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Example:
```
feat(dispatcher): Add streaming checkpoint support

Implement incremental token tracking for streaming responses.
This ensures accurate billing even if streams are interrupted.

Closes #42
```

## Areas to Contribute

### High Priority

- [ ] Streaming Dispatcher (Go) with incremental checkpointing
- [ ] Mastra-based Routing Service with CRISPE prompts
- [ ] EEOC compliance module with bias monitoring
- [ ] GDPR consent management APIs
- [ ] Enkrypt AI Guardrails integration

### Medium Priority

- [ ] Qdrant semantic cache implementation
- [ ] A/B Testing Dashboard component
- [ ] Real-time Monitoring Dashboard
- [ ] k6 load testing suite
- [ ] OpenTelemetry tracing integration

### Documentation

- [ ] API reference documentation
- [ ] Architecture deep-dive guides
- [ ] Deployment guides for AWS/GCP/Azure
- [ ] Troubleshooting guides
- [ ] Video tutorials

## Questions?

- Open an issue for bug reports or feature requests
- Join our [Slack community](https://ledgerline.slack.com)
- Email: dev@ledgerline.ai

Thank you for contributing to Ledgerline! 🚀
