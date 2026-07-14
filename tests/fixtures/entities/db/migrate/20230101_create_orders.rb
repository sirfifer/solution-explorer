class CreateOrders < ActiveRecord::Migration[7.0]
  def change
    create_table :orders do |t|
      t.string :status
      t.decimal :total
      t.integer :user_id
    end
  end
end
