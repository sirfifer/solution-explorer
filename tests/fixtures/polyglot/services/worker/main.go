// Package main is a background worker for the polyglot fixture.
package main

import "fmt"

// Job represents a unit of background work.
type Job struct {
	ID   int
	Name string
}

// Run executes the job and reports completion.
func (j Job) Run() string {
	return fmt.Sprintf("ran job %d: %s", j.ID, j.Name)
}

func main() {
	job := Job{ID: 1, Name: "cleanup"}
	fmt.Println(job.Run())
}
