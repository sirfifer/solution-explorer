import { Entity, Column, PrimaryGeneratedColumn } from "typeorm";

@Entity()
export class Account {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  username: string;

  @Column()
  balance: number;
}
