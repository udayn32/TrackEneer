import Header from "./components/Header"
import NextTask from "./components/Schedule"
import RecentFiles from "./components/Study"
export default function Home(){
  return(
    <main className="pt-8">
      <Header />
      <div className="mt-8 flex gap-8">
        <NextTask />
        <RecentFiles />
      </div>
    </main>
  )
}