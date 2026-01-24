-- Investment Logs table for gamification and journaling
-- Tracks deposits, trades, milestones, and badges

CREATE TYPE investmentlogtype AS ENUM (
    'DEPOSIT',
    'BUY', 
    'SELL',
    'DIVIDEND',
    'MILESTONE',
    'BADGE'
);

CREATE TABLE IF NOT EXISTS investment_logs (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
    log_type investmentlogtype NOT NULL,
    ticker VARCHAR(20),
    amount FLOAT,
    shares FLOAT,
    price FLOAT,
    emotion_tag VARCHAR(100),
    note VARCHAR(500),
    badge_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_investment_logs_portfolio ON investment_logs(portfolio_id);
CREATE INDEX idx_investment_logs_created ON investment_logs(created_at);
CREATE INDEX idx_investment_logs_type ON investment_logs(log_type);
