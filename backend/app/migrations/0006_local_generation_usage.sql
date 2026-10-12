ALTER TABLE retrieval_runs
    ADD COLUMN input_tokens integer CHECK (input_tokens >= 0),
    ADD COLUMN output_tokens integer CHECK (output_tokens >= 0),
    ADD COLUMN answer_model_digest text CHECK (answer_model_digest ~ '^[a-f0-9]{64}$');
ALTER TABLE chat_turns
    ADD COLUMN answer_model_digest text CHECK (answer_model_digest ~ '^[a-f0-9]{64}$'),
    ADD CONSTRAINT chat_input_tokens_nonnegative CHECK (input_tokens >= 0),
    ADD CONSTRAINT chat_output_tokens_nonnegative CHECK (output_tokens >= 0);
