module example.com/app

go 1.22

require (
	github.com/gorilla/mux v1.8.0
	github.com/sirupsen/logrus v1.9.0
)

replace github.com/gorilla/mux => github.com/myfork/mux v1.8.1

replace github.com/sirupsen/logrus => ./vendored/logrus
