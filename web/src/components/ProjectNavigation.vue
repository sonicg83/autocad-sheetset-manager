<script setup lang="ts">
import type {Subset} from "../api/contracts";
defineProps<{subsets:Subset[];selectedId:string}>();
defineEmits<{select:[subsetId:string]}>();
</script>
<template><aside aria-label="项目导航"><button v-for="subset in subsets" :key="subset.id" :class="{active:selectedId===subset.id}" @click="$emit('select',subset.id)">{{subset.display_name}} <b>{{subset.sheets.length}}</b></button></aside></template>
