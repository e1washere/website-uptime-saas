# Website Uptime Monitoring SaaS

A Flask-based SaaS application for monitoring website uptime with email notifications and Stripe payment integration.

## Features

- 🔐 User registration and authentication
- 📊 Monitor up to 3 websites per user
- ⏱️ Automatic checks every 5 minutes
- 📧 Email notifications when sites go down
- 💳 Stripe integration for monthly subscriptions ($5/month)
- 🎁 7-day free trial (no credit card required)
- 🎨 Clean, responsive UI with Bootstrap

## Prerequisites

- Python 3.8 or higher
- Gmail account for sending emails
- Stripe account for payment processing

## Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd website-uptime-saas
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp env.example .env
# Edit .env with your actual values
```

5. Run the application:
```bash
python app.py
```

The app will be available at `http://localhost:5000`

## Configuration

### Gmail SMTP Setup

1. Enable 2-factor authentication on your Gmail account
2. Generate an app-specific password:
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Copy the generated password
3. Update `.env`:
   ```
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-16-character-app-password
   ```

### Stripe Setup

1. Create a Stripe account at https://stripe.com
2. Get your API keys from the [Stripe Dashboard](https://dashboard.stripe.com/apikeys)
3. Create a product and price:
   - Go to Products in your Stripe Dashboard
   - Create a new product (e.g., "Website Monitoring")
   - Add a recurring price of $5/month
   - Copy the price ID (starts with `price_`)
4. Update `.env`:
   ```
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PRICE_ID=price_...
   ```
5. Set up webhook (for production):
   - Add webhook endpoint: `https://yourdomain.com/stripe-webhook`
   - Select events: `customer.subscription.deleted`, `customer.subscription.updated`
   - Copy the signing secret to `STRIPE_WEBHOOK_SECRET`

## Deployment

### Option 1: Deploy to Railway.app (Recommended)

1. Install Railway CLI:
```bash
npm install -g @railway/cli
```

2. Login and initialize:
```bash
railway login
railway init
```

3. Add environment variables:
```bash
railway variables set SECRET_KEY="your-secret-key"
railway variables set MAIL_USERNAME="your-email@gmail.com"
railway variables set MAIL_PASSWORD="your-app-password"
# Add all other variables from .env
```

4. Deploy:
```bash
railway up
```

### Option 2: Deploy to Render.com

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Configure:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
4. Add environment variables in the Render dashboard
5. Deploy!

### Option 3: Deploy to Heroku

1. Create `Procfile`:
```
web: gunicorn app:app
```

2. Initialize Heroku app:
```bash
heroku create your-app-name
heroku config:set SECRET_KEY="your-secret-key"
# Set all other environment variables
```

3. Deploy:
```bash
git push heroku main
```

## Database Management

The app uses SQLite for simplicity. The database file (`uptime_monitor.db`) is created automatically on first run.

For production, consider migrating to PostgreSQL:
1. Update `SQLALCHEMY_DATABASE_URI` in app.py
2. Install `psycopg2-binary` package
3. Update your deployment platform's database configuration

## Testing Stripe Integration

Use Stripe's test card numbers:
- Success: `4242 4242 4242 4242`
- Decline: `4000 0000 0000 0002`

Test webhooks locally using Stripe CLI:
```bash
stripe listen --forward-to localhost:5000/stripe-webhook
```

## Troubleshooting

### Email not sending?
- Ensure 2FA is enabled on Gmail
- Check app password is correct
- Verify "Less secure app access" is not blocking (use app passwords instead)

### Stripe not working?
- Verify you're using the correct API keys (test vs live)
- Check the price ID matches your Stripe product
- Ensure webhook secret is set correctly

### Background tasks not running?
- Check APScheduler is installed
- Verify no errors in console logs
- Ensure the scheduler is started (check app.py)

## Security Considerations

1. **Never commit `.env` file** - It's in `.gitignore` for a reason
2. **Use strong SECRET_KEY** - Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
3. **Enable HTTPS in production** - Required for Stripe
4. **Validate user input** - Current implementation has basic validation
5. **Rate limit API endpoints** - Consider adding Flask-Limiter for production

## Future Enhancements

- Multiple check locations
- SMS notifications
- Uptime statistics and graphs
- Custom check intervals
- API access
- Team accounts
- Status pages

## License

MIT License - See LICENSE file for details

## Support

For issues or questions, please open a GitHub issue or contact support. 