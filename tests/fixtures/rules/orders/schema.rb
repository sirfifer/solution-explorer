# Rails schema fixture: io constraints via column options (Ruby).

ActiveRecord::Schema.define(version: 1) do
  create_table "orders" do |t|
    t.string "email", limit: 255, null: false
    t.decimal "total", default: 0
  end
end
