package main

import "gorm.io/gorm"

type Order struct {
	gorm.Model
	Status   string `gorm:"index"`
	Total    float64
	UserID   uint
}
