// pinger — маленький сервис проверки связи. Код не менять.
// GET /ping → «pong 1.4.2»
package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
)

const version = "1.4.2"

func main() {
	http.HandleFunc("/ping", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "pong %s\n", version)
	})
	go func() {
		c := make(chan os.Signal, 1)
		signal.Notify(c, syscall.SIGTERM, os.Interrupt)
		<-c
		log.Print("остановка")
		os.Exit(0)
	}()
	log.Printf("pinger %s слушает :8080", version)
	log.Fatal(http.ListenAndServe(":8080", nil))
}
