ActiveRecord::Schema.define(version: 2023_01_01_000000) do
  create_table "comments", force: :cascade do |t|
    t.string "body"
    t.integer "article_id"
    t.datetime "created_at"
  end
end
