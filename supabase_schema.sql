-- ========================================
-- LUMINA FLOW - SIMPLIFIED SCHEMA (Quotation Generator MVP)
-- Execute this in Supabase SQL Editor
-- ========================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ========================================
-- PROFILES TABLE
-- ========================================

CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    plan TEXT DEFAULT 'free' CHECK (plan IN ('free', 'pro')),
    subscription_status TEXT DEFAULT 'inactive' CHECK (subscription_status IN ('active', 'inactive', 'trial')),
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT profiles_user_id_unique UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS profiles_user_id_idx ON public.profiles(user_id);

CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS profiles_updated_at ON public.profiles;
CREATE TRIGGER profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (user_id, email, full_name)
    VALUES (NEW.id, NEW.email, NEW.raw_user_meta_data->>'full_name');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- ========================================
-- QUOTATIONS TABLE
-- ========================================

CREATE TABLE IF NOT EXISTS public.quotations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    client_name TEXT NOT NULL,
    service_description TEXT NOT NULL,
    value NUMERIC(12,2) NOT NULL,
    currency TEXT DEFAULT 'BRL' CHECK (currency IN ('BRL', 'GBP')),
    expiry_date DATE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'expired')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS quotations_user_id_idx ON public.quotations(user_id);
CREATE INDEX IF NOT EXISTS quotations_created_at_idx ON public.quotations(created_at);

-- ========================================
-- RLS POLICIES
-- ========================================

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own profile" ON public.profiles;
CREATE POLICY "Users can view own profile"
    ON public.profiles FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
CREATE POLICY "Users can update own profile"
    ON public.profiles FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Service role can manage profiles" ON public.profiles;
CREATE POLICY "Service role can manage profiles"
    ON public.profiles FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE public.quotations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own quotations" ON public.quotations;
CREATE POLICY "Users can view own quotations"
    ON public.quotations FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can create own quotations" ON public.quotations;
CREATE POLICY "Users can create own quotations"
    ON public.quotations FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own quotations" ON public.quotations;
CREATE POLICY "Users can update own quotations"
    ON public.quotations FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own quotations" ON public.quotations;
CREATE POLICY "Users can delete own quotations"
    ON public.quotations FOR DELETE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Service role can manage quotations" ON public.quotations;
CREATE POLICY "Service role can manage quotations"
    ON public.quotations FOR ALL USING (auth.role() = 'service_role');
