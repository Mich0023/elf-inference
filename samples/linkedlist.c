/* Lista enlazada de enteros. */
#include <stdio.h>
#include <stdlib.h>

typedef struct node { int value; struct node *next; } node_t;

node_t *create_node(int value) {
    node_t *n = malloc(sizeof *n);
    if (!n) return NULL;
    n->value = value; n->next = NULL;
    return n;
}

node_t *list_append(node_t *head, int value) {
    node_t *n = create_node(value);
    if (!head) return n;
    node_t *cur = head;
    while (cur->next) cur = cur->next;
    cur->next = n;
    return head;
}

int list_length(const node_t *head) {
    int n = 0;
    for (; head; head = head->next) n++;
    return n;
}

int list_sum(const node_t *head) {
    int s = 0;
    for (; head; head = head->next) s += head->value;
    return s;
}

node_t *list_reverse(node_t *head) {
    node_t *prev = NULL;
    while (head) { node_t *nx = head->next; head->next = prev; prev = head; head = nx; }
    return prev;
}

node_t *list_find(node_t *head, int value) {
    for (; head; head = head->next) if (head->value == value) return head;
    return NULL;
}

void list_free(node_t *head) {
    while (head) { node_t *nx = head->next; free(head); head = nx; }
}

void print_list(const node_t *head) {
    for (; head; head = head->next) printf("%d ", head->value);
    putchar('\n');
}

int main(void) {
    node_t *l = NULL;
    for (int i = 1; i <= 5; i++) l = list_append(l, i * 10);
    l = list_reverse(l);
    print_list(l);
    printf("len=%d sum=%d found=%d\n", list_length(l), list_sum(l), list_find(l, 30) != NULL);
    list_free(l);
    return 0;
}
